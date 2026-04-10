#!/usr/bin/env python3
"""
enrich_summaries.py — Week 2 feature: fetch detail pages and extract summaries.

The original crawlers only scrape the homepage/listing page, which gives
us {title, url, publishedAt} but NOT a summary. For a higher-quality feed,
we want a 1-2 sentence summary of each article's actual content.

Design:
  - Read feed/feed-digest.json (the aggregated feed)
  - For each article with empty summary, fetch the detail page
  - Extract the first <p> or meta description
  - Strip HTML, truncate to ~150 chars
  - Write the enriched feed back to feed/feed-digest.json

Constraints:
  - Rate limited to 1 req/sec per source (don't hammer)
  - Max total runtime: 300 seconds (5 minutes) — incremental enrichment
  - Individual failures don't block the pipeline
  - Skips articles that already have a summary
  - Only processes the top N articles to cap cost (default: 30)

This script is designed to be idempotent: running it multiple times on
the same feed will only enrich articles that don't yet have summaries.

Usage:
    python3 enrich_summaries.py feed/feed-digest.json

Exits 0 even on partial failures (it's opportunistic enrichment).
"""

from __future__ import annotations

import json
import re
import sys
import time
import traceback
from pathlib import Path

# Import shared utilities when run from the crawlers/ directory
try:
    from common import clean_text, fetch_html
except ImportError:
    # Fallback for cases where we're run from repo root
    sys.path.insert(0, str(Path(__file__).parent))
    from common import clean_text, fetch_html  # noqa: E402


MAX_ARTICLES_TO_ENRICH = 30   # cap cost per run
MAX_RUNTIME_SECONDS = 300     # 5-minute budget
PER_SOURCE_DELAY_SECONDS = 1.0  # politeness
SUMMARY_MAX_CHARS = 140

# Patterns that indicate a meta description is site-wide boilerplate,
# not an article-specific summary. Many Chinese news sites share one
# meta description across all pages describing the site itself.
BOILERPLATE_MARKERS = re.compile(
    r"主管|主办|门户网站|新闻网站|刊载资质|国务院新闻办|国家能源局主管|"
    r"中国能源传媒|中电传媒"
)


def _is_boilerplate(text: str) -> bool:
    """Reject text that looks like site-wide boilerplate."""
    return bool(BOILERPLATE_MARKERS.search(text))


def extract_summary_from_html(html: str) -> str:
    """Best-effort extraction of a 1-sentence summary from a news detail page.

    Strategy (ordered by preference):
      1. First <p> with ≥ 40 CJK characters that is NOT boilerplate
         (this catches the actual article lede)
      2. og:description meta tag if not boilerplate
      3. meta name="description" if not boilerplate (last resort —
         often site-wide copy on Chinese news sites)
    """
    if not html:
        return ""

    # 1. First substantial <p> — the most reliable per-article source
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL)
    for p_html in paragraphs:
        p_text = re.sub(r"<[^>]+>", "", p_html)  # strip inner tags
        p_text = clean_text(p_text)
        cjk_count = sum(1 for c in p_text if "\u4e00" <= c <= "\u9fff")
        if cjk_count >= 40 and not _is_boilerplate(p_text):
            return p_text[:SUMMARY_MAX_CHARS]

    # 2. og:description (usually per-article on modern sites)
    og_m = re.search(
        r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    if og_m:
        text = clean_text(og_m.group(1))
        if 20 < len(text) < 500 and not _is_boilerplate(text):
            return text[:SUMMARY_MAX_CHARS]

    # 3. meta name="description" as last resort
    meta_m = re.search(
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    if meta_m:
        text = clean_text(meta_m.group(1))
        if 20 < len(text) < 500 and not _is_boilerplate(text):
            return text[:SUMMARY_MAX_CHARS]

    return ""


def enrich_feed(feed_path: Path) -> tuple[int, int]:
    """Enrich the feed in-place. Returns (enriched, attempted).

    Only articles with an empty summary field are processed.
    Results are written back to the same file.
    """
    with feed_path.open(encoding="utf-8") as f:
        feed = json.load(f)

    articles = feed.get("articles", [])
    to_enrich = [
        (i, a) for i, a in enumerate(articles)
        if not a.get("summary") and a.get("url")
    ][:MAX_ARTICLES_TO_ENRICH]

    if not to_enrich:
        print("No articles need enrichment — all already have summaries.",
              file=sys.stderr)
        return (0, 0)

    print(
        f"Enriching up to {len(to_enrich)} articles "
        f"(out of {len(articles)} total, "
        f"budget: {MAX_RUNTIME_SECONDS}s)...",
        file=sys.stderr,
    )

    enriched = 0
    start_time = time.monotonic()
    last_request_times: dict[str, float] = {}

    for idx, article in to_enrich:
        # Respect total runtime budget
        if time.monotonic() - start_time > MAX_RUNTIME_SECONDS:
            print(
                f"⏱  Runtime budget reached at {enriched}/{len(to_enrich)} articles.",
                file=sys.stderr,
            )
            break

        source = article.get("source", "unknown")
        url = article["url"]

        # Per-source rate limiting
        now = time.monotonic()
        last = last_request_times.get(source, 0)
        wait = (last + PER_SOURCE_DELAY_SECONDS) - now
        if wait > 0:
            time.sleep(wait)
        last_request_times[source] = time.monotonic()

        try:
            html = fetch_html(url, timeout=15)
            summary = extract_summary_from_html(html)
            if summary:
                articles[idx]["summary"] = summary
                enriched += 1
                print(f"  ✓ [{source}] {article['title'][:30]}", file=sys.stderr)
            else:
                print(f"  ∅ [{source}] {article['title'][:30]} — no summary found",
                      file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(
                f"  ✗ [{source}] {article['title'][:30]} — {type(e).__name__}",
                file=sys.stderr,
            )

    # Write enriched feed back
    with feed_path.open("w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)

    return (enriched, len(to_enrich))


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python3 enrich_summaries.py <feed.json>",
            file=sys.stderr,
        )
        return 2

    feed_path = Path(sys.argv[1])
    if not feed_path.exists():
        print(f"Feed file not found: {feed_path}", file=sys.stderr)
        return 2

    try:
        enriched, attempted = enrich_feed(feed_path)
        print(
            f"✓ Enrichment done: {enriched}/{attempted} summaries added",
            file=sys.stderr,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Enrichment encountered an error (exiting 0 anyway): {e}",
              file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    return 0  # never block the pipeline on enrichment failures


if __name__ == "__main__":
    sys.exit(main())
