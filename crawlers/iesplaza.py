#!/usr/bin/env python3
"""
Crawler for IESPlaza 综合能源服务网 (iesplaza.com).

Day 2 addition: vertical source for 综合能源 / 虚拟电厂 / 零碳园区 topics,
which complements cpnn.com.cn (generalist grid media) and nea.gov.cn (policy).

Status: ✅ No WAF, direct crawl works.
Article URL pattern: /article-<id>-<page>.html
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
    fetch_html,
    utc_now_iso,
)

SOURCE = "iesplaza.com"
SOURCE_NAME = "IESPlaza 综合能源服务网"
BASE_URL = "https://www.iesplaza.com/"
LOOKBACK_HOURS = 72  # 综合能源 niche updates slower than mainstream grid

ENERGY_KEYWORDS = re.compile(
    r"综合能源|虚拟电厂|VPP|零碳|光储|储能|绿电|充电|换电|"
    r"电网|电力|能源|微电网|源网荷储|数字能源|智慧能源|碳|"
    r"光伏|风电|氢能|核电|水电|配电|调度"
)

# iesplaza article URLs look like /article-18829-1.html
ARTICLE_URL_RE = re.compile(r"/article-\d+-\d+\.html$")


def crawl() -> dict:
    html = fetch_html(BASE_URL)
    waf = detect_waf(html)
    if waf:
        return empty_feed(SOURCE, SOURCE_NAME, error=f"WAF detected: {waf}")

    pattern = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,100})</a>',
        re.IGNORECASE,
    )
    raw_matches = pattern.findall(html)

    seen: set[str] = set()
    articles: list[dict] = []

    for href, raw_title in raw_matches:
        title = clean_text(raw_title)
        # Many Chinese sites HTML-encode quotes as &ldquo; / &rdquo;;
        # clean_text already unescapes them.
        if not title or not ENERGY_KEYWORDS.search(title):
            continue

        url = urljoin(BASE_URL, href)
        # Only article URLs (with the /article-NNN-N.html pattern)
        if not ARTICLE_URL_RE.search(url):
            continue
        if "iesplaza.com" not in url:
            continue

        if url in seen:
            continue
        seen.add(url)

        # iesplaza doesn't expose publish date in the URL, so leave null
        # and let aggregate.py handle ordering by source + sequence
        articles.append(
            {
                "id": f"iesplaza-{url.rsplit('-', 2)[-2] if '-' in url else url[-20:]}",
                "title": title,
                "url": url,
                "summary": "",
                "publishedAt": None,
                "source": SOURCE,
            }
        )

    # No chronological ordering available; preserve homepage order which
    # is typically newest-first.

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
