#!/usr/bin/env python3
"""
Crawler for 国家能源局 (nea.gov.cn).

Strategy:
- Fetch the homepage (no WAF)
- Extract article links (paths look like 20260410/hash/c.html)
- Filter by energy keywords in the title
- Build absolute URLs (homepage uses relative paths)
"""

from __future__ import annotations

import re
import sys
import traceback
from urllib.parse import urljoin

from common import (
    clean_text,
    detect_waf,
    emit,
    empty_feed,
    extract_date_from_url,
    fetch_html,
    utc_now_iso,
)

SOURCE = "nea.gov.cn"
SOURCE_NAME = "国家能源局"
BASE_URL = "https://www.nea.gov.cn/"
LOOKBACK_HOURS = 72  # policy pages update slower, widen the window

ENERGY_KEYWORDS = re.compile(
    r"能源|电力|电网|储能|风电|光伏|核电|可再生|新能源|发电|"
    r"煤炭|油气|氢能|碳|调度|市场"
)


def crawl() -> dict:
    html = fetch_html(BASE_URL)
    waf = detect_waf(html)
    if waf:
        return empty_feed(SOURCE, SOURCE_NAME, error=f"WAF detected: {waf}")

    # NEA uses URLs like: 20260410/<hash>/c.html
    pattern = re.compile(
        r'<a[^>]+href="([^"]+c\.html)"[^>]*>([^<]{6,80})</a>',
        re.IGNORECASE,
    )
    raw_matches = pattern.findall(html)

    seen: set[str] = set()
    articles: list[dict] = []

    for href, raw_title in raw_matches:
        title = clean_text(raw_title)
        if not ENERGY_KEYWORDS.search(title):
            continue

        url = urljoin(BASE_URL, href)
        if url in seen:
            continue
        seen.add(url)

        published_at = extract_date_from_url(url)

        articles.append(
            {
                "id": f"nea-{href.replace('/', '-').replace('.html', '')}",
                "title": title,
                "url": url,
                "summary": "",
                "publishedAt": published_at,
                "source": SOURCE,
            }
        )

    articles.sort(key=lambda a: (a["publishedAt"] or "0000"), reverse=True)

    return {
        "source": SOURCE,
        "sourceName": SOURCE_NAME,
        "generatedAt": utc_now_iso(),
        "lookbackHours": LOOKBACK_HOURS,
        "articles": articles,
        "stats": {"articleCount": len(articles)},
        "errors": [],
    }


if __name__ == "__main__":
    try:
        emit(crawl())
    except Exception as e:  # noqa: BLE001
        emit(empty_feed(SOURCE, SOURCE_NAME, error=f"{type(e).__name__}: {e}"))
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(0)
