#!/usr/bin/env python3
"""
Crawler for 电网头条 (cpnn.com.cn).

Strategy:
- Fetch the homepage (no WAF as of 2026-04-11)
- Extract all <a href="..."> links with Chinese anchor text
- Filter by energy-related keywords
- Normalize relative URLs (e.g. ./news/xwtt/202604/t20260410_xxx.html)
- Extract publish date from the URL pattern
- Deduplicate by URL
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

SOURCE = "cpnn.com.cn"
SOURCE_NAME = "电网头条（中国能源传媒集团）"
BASE_URL = "https://www.cpnn.com.cn/"
LOOKBACK_HOURS = 48

# Words that indicate the link is an energy-industry article we want.
ENERGY_KEYWORDS = re.compile(
    r"电力|电网|能源|储能|风电|光伏|核电|可再生|新能源|发电|输电|"
    r"配电|绿电|碳|算力|虚拟电厂|抽蓄|氢能"
)

# Words that indicate site chrome / navigation we should skip.
CHROME_KEYWORDS = re.compile(
    r"^(首页|登录|注册|关于|联系|投稿|English|版权|ICP|主办|主管|Copyright)"
)


def crawl() -> dict:
    html = fetch_html(BASE_URL)
    waf = detect_waf(html)
    if waf:
        return empty_feed(SOURCE, SOURCE_NAME, error=f"WAF detected: {waf}")

    # Match <a href="X">Y</a> where Y is 6-80 chars of visible text.
    pattern = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,80})</a>',
        re.IGNORECASE,
    )
    raw_matches = pattern.findall(html)

    seen_urls: set[str] = set()
    articles: list[dict] = []

    for href, raw_title in raw_matches:
        title = clean_text(raw_title)
        if not title or CHROME_KEYWORDS.match(title):
            continue
        if not ENERGY_KEYWORDS.search(title):
            continue

        url = urljoin(BASE_URL, href)
        # Only keep cpnn.com.cn articles; external links are noise.
        if "cpnn.com.cn" not in url:
            continue
        # Only keep article URLs (they end in .html and contain a date).
        if not url.endswith(".html"):
            continue

        published_at = extract_date_from_url(url)
        if not published_at:
            continue  # skip navigation pages without dates

        if url in seen_urls:
            continue
        seen_urls.add(url)

        articles.append(
            {
                "id": f"cpnn-{url.rsplit('/', 1)[-1].replace('.html', '')}",
                "title": title,
                "url": url,
                "summary": "",  # detail page needed for summary; skip in v1
                "publishedAt": published_at,
                "source": SOURCE,
            }
        )

    # Sort newest first
    articles.sort(key=lambda a: a["publishedAt"], reverse=True)

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
    except Exception as e:  # noqa: BLE001 — crawlers must never raise
        emit(empty_feed(SOURCE, SOURCE_NAME, error=f"{type(e).__name__}: {e}"))
        print(traceback.format_exc(), file=sys.stderr)
        # Exit 0 so GitHub Actions continues to the next crawler
        sys.exit(0)
