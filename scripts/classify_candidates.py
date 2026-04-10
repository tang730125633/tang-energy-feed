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


def classify_all(feed: dict) -> dict:
    """Walk the feed.articles list and build 4 candidate pools."""
    articles = feed.get("articles", [])
    candidates: dict[str, list[dict]] = {
        "top3": [],
        "policy": [],
        "hubei": [],
        "hubei_neighbor": [],
        "ai_power": [],
    }

    for article in articles:
        if not within_lookback(article, hours=48):
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
    if len(sys.argv) != 2:
        print(
            "Usage: python3 classify_candidates.py <feed.json> > candidates.json",
            file=sys.stderr,
        )
        return 2
    feed_path = Path(sys.argv[1])
    if not feed_path.exists():
        print(f"Feed file not found: {feed_path}", file=sys.stderr)
        return 2

    with feed_path.open(encoding="utf-8") as f:
        feed = json.load(f)

    result = classify_all(feed)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")

    counts = result["stats"]["candidateCounts"]
    print(
        f"✓ Classified: top3={counts['top3']}, policy={counts['policy']}, "
        f"hubei={counts['hubei']}, ai_power={counts['ai_power']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
