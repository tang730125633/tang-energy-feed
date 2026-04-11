#!/usr/bin/env python3
"""
archive.py — post-send archival step for the daily digest pipeline.

Called by run.sh AFTER the Feishu message has been successfully delivered.
Performs four things, all idempotent:

  1. Writes three files to archive/YYYY/MM/:
     - YYYY-MM-DD-input.json  ← machine-readable AI output (for replay/analysis)
     - YYYY-MM-DD.md          ← human-readable markdown (GitHub-previewable)
     - YYYY-MM-DD-meta.json   ← audit metadata (timestamps, message id, model)

  2. Updates archive/seen-urls.json — a rolling 7-day window of URLs that
     have already been selected for a digest. classify_candidates.py reads
     this file to exclude recently-used articles from tomorrow's candidates.

  3. Prunes seen-urls.json entries older than the TTL window (7 days).

  4. Writes .last-sent-date (repo root) to today's date, so a second run
     on the same day (e.g. the 11:00 backup launchd trigger) knows to skip.

Design notes:
  - Never raises. Archival failures should be reported but must not cause
    run.sh to return non-zero — the message has already been sent to the
    user's group, and a failed archive is a WARN, not an ERROR.
  - All writes are atomic (write-to-tempfile + os.rename) so a Ctrl-C
    midway through won't leave a half-written JSON.
  - seen-urls.json starts empty on day 1; the TTL pruning happens
    automatically from day 8 onwards.

Usage:
    python3 archive.py \\
        --input /tmp/input.json \\
        --message-id om_xxx \\
        --chat-id oc_xxx \\
        --feed-generated-at "2026-04-11T06:00:00+08:00" \\
        --feed-total-articles 230 \\
        --model gemini-3-flash-preview
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Rolling window for URL-level dedup.
# Configurable via the --ttl-days flag.
DEFAULT_TTL_DAYS = 7

# Chinese-time display for sentAt. We still store the ISO timestamp;
# this is only for the meta block in the .md file.
LOCAL_TZ_OFFSET_HOURS = 8


def repo_root() -> Path:
    """Return the absolute path to the repo root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def local_iso_now() -> str:
    """Return current local time (UTC+8) as ISO 8601 with offset."""
    tz = dt.timezone(dt.timedelta(hours=LOCAL_TZ_OFFSET_HOURS))
    return dt.datetime.now(tz).isoformat(timespec="seconds")


def today_local_date_str() -> str:
    """Return today's date in local (Beijing) time as YYYY-MM-DD."""
    tz = dt.timezone(dt.timedelta(hours=LOCAL_TZ_OFFSET_HOURS))
    return dt.datetime.now(tz).date().isoformat()


def atomic_write_text(path: Path, content: str) -> None:
    """Write text to a file atomically (tempfile + rename).

    This guarantees that readers never see a half-written file even if
    this process is interrupted.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        f.write(content)
    os.rename(tmp_path, path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Metadata file
# ---------------------------------------------------------------------------

def build_meta(
    *,
    date: str,
    message_id: str,
    chat_id: str,
    feed_generated_at: str,
    feed_total_articles: int,
    model: str,
    articles_used: int,
) -> dict[str, Any]:
    return {
        "date": date,
        "sentAt": local_iso_now(),
        "messageId": message_id,
        "chatId": chat_id,
        "model": model,
        "feedGeneratedAt": feed_generated_at,
        "feedTotalArticles": feed_total_articles,
        "articlesUsed": articles_used,
    }


# ---------------------------------------------------------------------------
# seen-urls.json (Q3b rolling dedup cache)
# ---------------------------------------------------------------------------

def load_seen_urls(path: Path) -> dict[str, Any]:
    """Load the seen-urls cache, creating it if missing."""
    if not path.exists():
        return {
            "description": (
                "Rolling dedup cache: URLs already used in a digest within "
                "the TTL window. classify_candidates.py reads this file "
                "and excludes these URLs from tomorrow's candidate pools."
            ),
            "ttlDays": DEFAULT_TTL_DAYS,
            "entries": [],
        }
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
            if "entries" not in data:
                data["entries"] = []
            if "ttlDays" not in data:
                data["ttlDays"] = DEFAULT_TTL_DAYS
            return data
    except (OSError, json.JSONDecodeError) as e:
        print(
            f"  ⚠ Could not parse seen-urls.json ({e}), starting fresh",
            file=sys.stderr,
        )
        return {
            "description": "Rolling dedup cache (regenerated after parse error)",
            "ttlDays": DEFAULT_TTL_DAYS,
            "entries": [],
        }


def prune_stale_entries(
    seen: dict[str, Any], today_str: str, ttl_days: int
) -> int:
    """Remove entries whose firstSeen is older than ttl_days. Returns count pruned."""
    today = dt.date.fromisoformat(today_str)
    cutoff = today - dt.timedelta(days=ttl_days)

    before = len(seen["entries"])
    seen["entries"] = [
        e for e in seen["entries"]
        if _entry_is_within(e, cutoff)
    ]
    return before - len(seen["entries"])


def _entry_is_within(entry: dict, cutoff: dt.date) -> bool:
    first_seen_str = entry.get("firstSeen", "")
    try:
        first_seen = dt.date.fromisoformat(first_seen_str)
    except ValueError:
        # Malformed entry — drop it
        return False
    return first_seen >= cutoff


def add_new_entries(
    seen: dict[str, Any], input_data: dict, today_str: str
) -> int:
    """Add today's digest URLs to seen, skipping any already present.

    Returns count of NEW entries added.
    """
    existing_urls = {e["url"] for e in seen["entries"]}
    sections = input_data.get("sections", {})

    new_count = 0
    for section_name in ("top3", "policy", "hubei", "ai_power"):
        items = sections.get(section_name, [])
        if not isinstance(items, list):
            continue
        for item in items:
            url = item.get("url")
            if not url or url in existing_urls:
                continue
            seen["entries"].append(
                {
                    "url": url,
                    "title": item.get("title", "")[:80],
                    "section": section_name,
                    "firstSeen": today_str,
                }
            )
            existing_urls.add(url)
            new_count += 1
    return new_count


# ---------------------------------------------------------------------------
# Markdown rendering (delegated to render_markdown.py)
# ---------------------------------------------------------------------------

def render_markdown_file(
    input_path: Path, meta_path: Path, out_path: Path
) -> None:
    """Call render_markdown.py as a subprocess. Captures stdout to out_path."""
    script = Path(__file__).parent / "render_markdown.py"
    result = subprocess.run(
        ["python3", str(script), str(input_path), str(meta_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    atomic_write_text(out_path, result.stdout)


# ---------------------------------------------------------------------------
# Main archive workflow
# ---------------------------------------------------------------------------

def archive(args: argparse.Namespace) -> int:
    root = repo_root()
    today_str = today_local_date_str()
    year, month, _ = today_str.split("-")

    archive_dir = root / "archive" / year / month
    archive_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"✗ Input file not found: {input_path}", file=sys.stderr)
        return 1

    with input_path.open(encoding="utf-8") as f:
        input_data = json.load(f)

    # Count articles used (sanity — should be exactly 10)
    sections = input_data.get("sections", {})
    articles_used = sum(
        len(sections.get(name, []))
        for name in ("top3", "policy", "hubei", "ai_power")
    )

    # -----------------------------------------------------------------
    # 1. Write archive/YYYY/MM/YYYY-MM-DD-input.json
    # -----------------------------------------------------------------
    input_target = archive_dir / f"{today_str}-input.json"
    atomic_write_json(input_target, input_data)
    print(f"  ✓ Archived input → {input_target.relative_to(root)}", file=sys.stderr)

    # -----------------------------------------------------------------
    # 2. Write archive/YYYY/MM/YYYY-MM-DD-meta.json
    # -----------------------------------------------------------------
    meta = build_meta(
        date=today_str,
        message_id=args.message_id,
        chat_id=args.chat_id,
        feed_generated_at=args.feed_generated_at,
        feed_total_articles=args.feed_total_articles,
        model=args.model,
        articles_used=articles_used,
    )
    meta_target = archive_dir / f"{today_str}-meta.json"
    atomic_write_json(meta_target, meta)
    print(f"  ✓ Archived meta → {meta_target.relative_to(root)}", file=sys.stderr)

    # -----------------------------------------------------------------
    # 3. Write archive/YYYY/MM/YYYY-MM-DD.md (human-readable)
    # -----------------------------------------------------------------
    md_target = archive_dir / f"{today_str}.md"
    try:
        render_markdown_file(input_target, meta_target, md_target)
        print(f"  ✓ Archived markdown → {md_target.relative_to(root)}", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(
            f"  ⚠ render_markdown.py failed (WARN, not fatal): {e.stderr}",
            file=sys.stderr,
        )

    # -----------------------------------------------------------------
    # 4. Update seen-urls.json (dedup cache)
    # -----------------------------------------------------------------
    seen_path = root / "archive" / "seen-urls.json"
    seen = load_seen_urls(seen_path)

    pruned = prune_stale_entries(seen, today_str, ttl_days=seen.get("ttlDays", DEFAULT_TTL_DAYS))
    new_count = add_new_entries(seen, input_data, today_str)
    atomic_write_json(seen_path, seen)
    print(
        f"  ✓ seen-urls.json: +{new_count} new, -{pruned} pruned, "
        f"{len(seen['entries'])} total (TTL {seen.get('ttlDays', DEFAULT_TTL_DAYS)}d)",
        file=sys.stderr,
    )

    # -----------------------------------------------------------------
    # 5. Write .last-sent-date (run-level dedup)
    # -----------------------------------------------------------------
    last_sent_path = root / ".last-sent-date"
    atomic_write_text(last_sent_path, today_str + "\n")
    print(
        f"  ✓ .last-sent-date = {today_str} (today's report will not be re-sent)",
        file=sys.stderr,
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive a successfully-sent daily digest."
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to the AI remix output (input.json)",
    )
    parser.add_argument(
        "--message-id", required=True,
        help="Feishu message_id returned after successful send",
    )
    parser.add_argument(
        "--chat-id", required=True,
        help="Target Feishu chat_id",
    )
    parser.add_argument(
        "--feed-generated-at", default="",
        help="ISO timestamp from the upstream feed's generatedAt field",
    )
    parser.add_argument(
        "--feed-total-articles", type=int, default=0,
        help="Total article count from the upstream feed's stats",
    )
    parser.add_argument(
        "--model", default="unknown",
        help="AI model name (e.g. gemini-3-flash-preview)",
    )
    args = parser.parse_args()

    try:
        return archive(args)
    except Exception as e:  # noqa: BLE001
        # Archival should NEVER crash the run.sh pipeline. Log the error
        # prominently but exit 0 so run.sh treats it as "send succeeded,
        # archive partially failed" rather than "total failure".
        print(
            f"✗ Archive step raised unexpectedly (non-fatal): "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
