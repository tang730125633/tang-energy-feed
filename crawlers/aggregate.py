#!/usr/bin/env python3
"""
Aggregate all individual feed-*.json files into:
  1. feed-digest.json          — unified all-sources feed
  2. feed-central-energy.json   — Month 2 feature: Hubei + neighbors only

Usage:
    python3 aggregate.py <feed_dir>

Reads every feed-*.json in the directory (except the outputs themselves),
merges the articles, dedupes by URL, sorts newest-first, pulls the copper
block from feed-copper.json, and writes feed-digest.json to stdout.

Additionally writes feed-central-energy.json alongside feed-digest.json,
which contains only articles whose title mentions a central-China province:
湖北 / 湖南 / 河南 / 江西 / 安徽 (or their capital cities / 华中).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from common import utc_now_iso

# -----------------------------------------------------------------------------
# Output file names (these are excluded when reading inputs, to avoid loops)
# -----------------------------------------------------------------------------
DIGEST_FILENAME = "feed-digest.json"
CENTRAL_ENERGY_FILENAME = "feed-central-energy.json"
OUTPUT_FILENAMES = {DIGEST_FILENAME, CENTRAL_ENERGY_FILENAME}

# -----------------------------------------------------------------------------
# Month 2: Central China (中部地区) province filter
# -----------------------------------------------------------------------------
# Narrow definition: the 5 核心中部 provinces + 华中 umbrella term.
# Each entry has a region tag so the downstream consumer can show
# province-specific breakdowns.
CENTRAL_PROVINCE_REGEX = {
    "湖北": re.compile(r"湖北|武汉|宜昌|襄阳|荆州|黄石|孝感|鄂"),
    "湖南": re.compile(r"湖南|长沙|株洲|湘潭|衡阳|岳阳|湘"),
    "河南": re.compile(r"河南|郑州|洛阳|开封|南阳|新乡|豫"),
    "江西": re.compile(r"江西|南昌|九江|赣州|赣"),
    "安徽": re.compile(r"安徽|合肥|芜湖|蚌埠|皖"),
    "华中": re.compile(r"华中"),
}


def load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"_load_error": str(e), "articles": [], "errors": [str(e)]}


def tag_province(title: str) -> str | None:
    """Return the first matching central-China province tag, or None."""
    if not title:
        return None
    for province, pattern in CENTRAL_PROVINCE_REGEX.items():
        if pattern.search(title):
            return province
    return None


def aggregate(feed_dir: Path) -> tuple[dict, dict]:
    """Return (digest, central_energy_feed).

    Both feeds share the same underlying articles list, but
    central_energy is filtered to central-China provinces.
    """
    all_articles: list[dict] = []
    sources_info: list[dict] = []
    copper: dict | None = None
    all_errors: list[dict] = []

    for path in sorted(feed_dir.glob("feed-*.json")):
        if path.name in OUTPUT_FILENAMES:
            continue  # don't read our own outputs

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

        # Merge articles from this source
        for article in data.get("articles", []):
            all_articles.append(article)

        # Copper block lives only in feed-copper.json
        if source_id == "cjys.net" and data.get("copper"):
            copper = data["copper"]

    # Dedupe by URL, keep first occurrence (order preserved = source priority)
    seen: set[str] = set()
    unique: list[dict] = []
    for a in all_articles:
        url = a.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(a)

    # Sort newest-first (None dates sink to the bottom)
    unique.sort(
        key=lambda a: (a.get("publishedAt") or "0000-00-00"), reverse=True
    )

    # ---- Tag each article with province (used by both feeds) ----
    for a in unique:
        province = tag_province(a.get("title", ""))
        if province:
            a["province"] = province

    # ---- Stats for the main digest ----
    by_source: dict[str, int] = {}
    by_province: dict[str, int] = {}
    for a in unique:
        src = a.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1
        prov = a.get("province")
        if prov:
            by_province[prov] = by_province.get(prov, 0) + 1

    digest = {
        "generatedAt": utc_now_iso(),
        "sources": sources_info,
        "articles": unique,
        "copper": copper,
        "stats": {
            "totalArticles": len(unique),
            "bySource": by_source,
            "byProvince": by_province,
        },
        "errors": all_errors,
    }

    # ---- Month 2 feature: central-China-only feed ----
    central_articles = [a for a in unique if a.get("province")]
    central_by_province: dict[str, int] = {}
    for a in central_articles:
        p = a["province"]
        central_by_province[p] = central_by_province.get(p, 0) + 1

    central_feed = {
        "generatedAt": utc_now_iso(),
        "parentFeed": "feed-digest.json",
        "filter": "central_china_provinces",
        "provinces": sorted(CENTRAL_PROVINCE_REGEX.keys()),
        "articles": central_articles,
        "stats": {
            "totalArticles": len(central_articles),
            "byProvince": central_by_province,
        },
        "note": (
            "Filtered subset of feed-digest.json that mentions 湖北/湖南/河南/"
            "江西/安徽 (or 华中) in the title. Month 2 roadmap feature. "
            "Consumers who only care about central-China energy news should "
            "subscribe to THIS feed instead of feed-digest.json."
        ),
    }

    return digest, central_feed


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 aggregate.py <feed_dir>", file=sys.stderr)
        return 2
    feed_dir = Path(sys.argv[1])
    if not feed_dir.is_dir():
        print(f"Not a directory: {feed_dir}", file=sys.stderr)
        return 2

    digest, central = aggregate(feed_dir)

    # Write the main digest to stdout (preserves existing workflow contract:
    # daily-crawl.yml does `aggregate.py feed/ > feed/feed-digest.json`)
    sys.stdout.write(json.dumps(digest, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")

    # Write the central-energy feed directly to disk as a side effect.
    # This is additional — doesn't disturb the stdout contract.
    central_path = feed_dir / CENTRAL_ENERGY_FILENAME
    with central_path.open("w", encoding="utf-8") as f:
        json.dump(central, f, ensure_ascii=False, indent=2)

    # Stderr summary (workflow logs)
    print(
        f"✓ Aggregated: {digest['stats']['totalArticles']} total articles, "
        f"{central['stats']['totalArticles']} central-China articles. "
        f"copper={'yes' if digest.get('copper') else 'no'}, "
        f"sources={len(digest['sources'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
