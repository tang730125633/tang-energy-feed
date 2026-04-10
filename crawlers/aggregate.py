#!/usr/bin/env python3
"""
Aggregate all individual feed-*.json files into a single feed-digest.json.

Usage:
    python3 aggregate.py <feed_dir>

Reads every feed-*.json in the directory (except feed-digest.json itself),
merges the articles, dedupes by URL, sorts newest-first, pulls the copper
block from feed-copper.json, and writes feed-digest.json to stdout.

This is the one file downstream AIs (zero-carbon-daily-report skill,
戴总's AI, anyone else subscribing) should actually consume.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from common import utc_now_iso


def load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"_load_error": str(e), "articles": [], "errors": [str(e)]}


def aggregate(feed_dir: Path) -> dict:
    all_articles: list[dict] = []
    sources_info: list[dict] = []
    copper: dict | None = None
    all_errors: list[dict] = []

    for path in sorted(feed_dir.glob("feed-*.json")):
        if path.name == "feed-digest.json":
            continue
        data = load_json(path)

        source_id = data.get("source", path.stem.replace("feed-", ""))
        sources_info.append(
            {
                "id": source_id,
                "name": data.get("sourceName", source_id),
                "generatedAt": data.get("generatedAt"),
                "articleCount": data.get("stats", {}).get("articleCount", 0),
                "hasErrors": bool(data.get("errors")),
            }
        )

        if data.get("errors"):
            all_errors.append({"source": source_id, "errors": data["errors"]})

        # Merge articles
        for article in data.get("articles", []):
            all_articles.append(article)

        # Pull copper block from the copper feed
        if source_id == "cjys.net" and data.get("copper"):
            copper = data["copper"]

    # Dedupe by URL, keep first occurrence
    seen: set[str] = set()
    unique: list[dict] = []
    for a in all_articles:
        url = a.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(a)

    # Sort newest first (None dates go last)
    unique.sort(
        key=lambda a: (a.get("publishedAt") or "0000-00-00"), reverse=True
    )

    # Build stats
    by_source: dict[str, int] = {}
    for a in unique:
        src = a.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    return {
        "generatedAt": utc_now_iso(),
        "sources": sources_info,
        "articles": unique,
        "copper": copper,
        "stats": {
            "totalArticles": len(unique),
            "bySource": by_source,
        },
        "errors": all_errors,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 aggregate.py <feed_dir>", file=sys.stderr)
        return 2
    feed_dir = Path(sys.argv[1])
    if not feed_dir.is_dir():
        print(f"Not a directory: {feed_dir}", file=sys.stderr)
        return 2
    digest = aggregate(feed_dir)
    sys.stdout.write(json.dumps(digest, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
