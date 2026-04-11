#!/usr/bin/env python3
"""
classify_candidates.py — Pre-classify feed articles into 4 section candidate pools.

This script does the DETERMINISTIC part of selection: keyword-based
pre-classification. It reads feed-digest.json, scores each article
against 4 sections (top3/policy/hubei/ai_power), and produces a
candidates.json with 5-10 candidates per section.

The AI then does the CREATIVE part: picking the final 3/3/2/2 from
these pools, rewriting titles, and generating impact analysis.

Why not let the AI classify everything from scratch? Two reasons:
  1. Token efficiency — 100 articles in context is expensive
  2. Determinism — keyword rules are consistent, AI classification drifts

Usage:
    python3 classify_candidates.py <feed.json> > /tmp/candidates.json
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Seen-URLs dedup (Q3b)
# ---------------------------------------------------------------------------
# Path of the rolling dedup cache, resolved relative to this script so it
# works regardless of the caller's cwd.
SEEN_URLS_PATH = Path(__file__).resolve().parent.parent / "archive" / "seen-urls.json"

# ---------------------------------------------------------------------------
# Section classification rules
# ---------------------------------------------------------------------------

# Each rule has a set of regex keywords. An article is a candidate for a
# section if ANY keyword matches its title. An article can appear in
# multiple sections' candidate pools — the AI will deduplicate during
# final selection.

TOP3_KEYWORDS = re.compile(
    r"可再生能源|装机|占比|突破|首次|新高|创历史|千瓦时|TWh|GW|全球首|"
    r"纪录|历史性|重大|全国|全球|亿千瓦"
)

POLICY_KEYWORDS = re.compile(
    r"政策|核准|座谈|部署|发布|意见|征求|规划|条例|办法|试点|"
    r"市场|交易|机制|补贴|监管|改革|方案|战略|规定|通知"
)

HUBEI_KEYWORDS = re.compile(r"湖北|武汉|宜昌|襄阳|荆州|黄石|鄂|华中")
HUBEI_NEIGHBOR_KEYWORDS = re.compile(
    r"湖南|长沙|河南|郑州|江西|南昌|安徽|合肥|陕西|西安|重庆|贵州|贵阳"
)

AI_POWER_KEYWORDS = re.compile(
    r"算电|算力|数据中心|虚拟电厂|VPP|绿电直供|源网荷储|AI.*电|电.*AI|"
    r"人工智能|智能电网|智慧能源|数字化|源网荷储一体化|零碳园区"
)

# Generic noise we definitely don't want
NOISE_KEYWORDS = re.compile(
    r"党组|理论学习|巡视|廉洁|作风|纪检|工会|团委|座右铭|招聘|讣告"
)

MAX_PER_SECTION = 10


def classify_article(article: dict) -> list[str]:
    """Return the list of sections this article is a candidate for.

    An article may match multiple sections. The AI picks the final
    placement during remix.
    """
    title = article.get("title", "")
    if not title or NOISE_KEYWORDS.search(title):
        return []

    matched = []

    if TOP3_KEYWORDS.search(title):
        matched.append("top3")
    if POLICY_KEYWORDS.search(title):
        matched.append("policy")
    if HUBEI_KEYWORDS.search(title):
        matched.append("hubei")
    elif HUBEI_NEIGHBOR_KEYWORDS.search(title):
        # Neighbor provinces are lower-priority candidates for hubei;
        # tag them separately so the AI knows they're backup fills
        matched.append("hubei_neighbor")
    if AI_POWER_KEYWORDS.search(title):
        matched.append("ai_power")

    return matched


def within_lookback(article: dict, hours: int = 48) -> bool:
    """Keep articles published within the last N hours. Unknown dates = keep."""
    published = article.get("publishedAt")
    if not published:
        return True
    try:
        d = dt.date.fromisoformat(published[:10])
    except ValueError:
        return True
    cutoff = dt.date.today() - dt.timedelta(days=max(1, hours // 24))
    return d >= cutoff


def load_seen_urls() -> set[str]:
    """Load the set of URLs that have already been used in a digest within
    the TTL window. Returns an empty set if the file doesn't exist (day 1)
    or cannot be parsed.

    This is called by classify_all() BEFORE building candidate pools, so
    any URL in this set is silently skipped — the AI never sees it, and
    tomorrow's digest cannot accidentally re-use a title from this week.
    """
    if not SEEN_URLS_PATH.exists():
        return set()
    try:
        with SEEN_URLS_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(
            f"  ⚠ Could not load seen-urls.json ({e}), skipping dedup filter",
            file=sys.stderr,
        )
        return set()

    # TTL-prune in memory (archive.py prunes on write; this is belt+suspenders)
    ttl_days = data.get("ttlDays", 7)
    cutoff = dt.date.today() - dt.timedelta(days=ttl_days)

    seen: set[str] = set()
    for entry in data.get("entries", []):
        first_seen_str = entry.get("firstSeen", "")
        try:
            first_seen = dt.date.fromisoformat(first_seen_str)
        except ValueError:
            continue
        if first_seen >= cutoff:
            url = entry.get("url")
            if url:
                seen.add(url)
    return seen


def classify_all(feed: dict, skip_dedup: bool = False) -> dict:
    """Walk the feed.articles list and build 4 candidate pools.

    In production mode (skip_dedup=False), filters out any URL already
    present in archive/seen-urls.json (rolling 7-day dedup window).
    This is the core of Q3b: the same news article can never be selected
    for two different daily digests within a week, even if the upstream
    feed keeps returning it.

    In test mode (skip_dedup=True, invoked via --no-dedup), the dedup
    filter is bypassed. This lets humans run test digests repeatedly
    without "stealing" content from tomorrow's production run.
    """
    articles = feed.get("articles", [])

    # Q3b: dedup filter (production only)
    if skip_dedup:
        print(
            "  → Dedup filter: DISABLED (--no-dedup, test mode)",
            file=sys.stderr,
        )
        seen_urls: set[str] = set()
    else:
        seen_urls = load_seen_urls()
        if seen_urls:
            print(
                f"  → Dedup filter: excluding {len(seen_urls)} recently-used URLs",
                file=sys.stderr,
            )

    candidates: dict[str, list[dict]] = {
        "top3": [],
        "policy": [],
        "hubei": [],
        "hubei_neighbor": [],
        "ai_power": [],
    }
    dedup_hits = 0

    for article in articles:
        if not within_lookback(article, hours=48):
            continue
        # Q3b: skip if this URL was used in a digest within the TTL window
        if article.get("url") in seen_urls:
            dedup_hits += 1
            continue
        sections = classify_article(article)
        for sec in sections:
            if len(candidates[sec]) >= MAX_PER_SECTION:
                continue
            # Strip fields the AI doesn't need
            slim = {
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "summary": article.get("summary", ""),
                "publishedAt": article.get("publishedAt", ""),
                "source": article.get("source", ""),
            }
            candidates[sec].append(slim)

    if dedup_hits:
        print(
            f"  → Dedup filter: dropped {dedup_hits} articles already used this week",
            file=sys.stderr,
        )

    # Merge hubei_neighbor as fallback into hubei if hubei pool is thin
    if len(candidates["hubei"]) < 2:
        need = 2 - len(candidates["hubei"])
        candidates["hubei"].extend(
            candidates["hubei_neighbor"][:need + 3]  # keep a few extra as options
        )
    # Drop the intermediate bucket from the output
    del candidates["hubei_neighbor"]

    return {
        "date": dt.date.today().isoformat(),
        "feed_generatedAt": feed.get("generatedAt"),
        "candidates": candidates,
        "copper": feed.get("copper"),
        "stats": {
            "candidateCounts": {k: len(v) for k, v in candidates.items()},
            "feedTotalArticles": feed.get("stats", {}).get("totalArticles", 0),
        },
        "upstream_errors": feed.get("errors", []),
    }


def main() -> int:
    # Simple manual arg parsing — avoids argparse just for one flag.
    args = sys.argv[1:]
    no_dedup = False
    if "--no-dedup" in args:
        no_dedup = True
        args.remove("--no-dedup")

    if len(args) != 1:
        print(
            "Usage: python3 classify_candidates.py [--no-dedup] <feed.json> > candidates.json",
            file=sys.stderr,
        )
        return 2
    feed_path = Path(args[0])
    if not feed_path.exists():
        print(f"Feed file not found: {feed_path}", file=sys.stderr)
        return 2

    with feed_path.open(encoding="utf-8") as f:
        feed = json.load(f)

    result = classify_all(feed, skip_dedup=no_dedup)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")

    counts = result["stats"]["candidateCounts"]
    mode = "test, no dedup" if no_dedup else "production, with dedup"
    print(
        f"✓ Classified ({mode}): top3={counts['top3']}, policy={counts['policy']}, "
        f"hubei={counts['hubei']}, ai_power={counts['ai_power']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
