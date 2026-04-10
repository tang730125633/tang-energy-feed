#!/usr/bin/env python3
"""
Crawler for 世纪新能源网 (ne21.com).

IMPORTANT — discovery on 2026-04-11:
ne21.com serves DIFFERENT content based on the client's User-Agent and
Accept-* headers. With a bare `curl` that sends only User-Agent, it
returns a 403 + JS redirect shell. But with `requests.get` using the
full browser-like headers from common.py (Accept-Language, Accept-
Encoding, etc), it returns the real 63KB homepage. So we don't need
Playwright for this source — the direct scrape works.

If GitHub Actions from a US IP gets the challenge page instead, this
crawler will detect it and fall through to the placeholder behavior.
In that case, the standalone bjx-crawl.yml workflow will handle ne21
via crawlers/ne21_playwright.py instead.

Status: ✅ Direct scrape works when headers are full (via common.fetch_html).
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

SOURCE = "ne21.com"
SOURCE_NAME = "世纪新能源网"
BASE_URL = "https://www.ne21.com/"
LOOKBACK_HOURS = 72  # niche source, lookback wider

ENERGY_KEYWORDS = re.compile(
    r"新能源|光伏|风电|储能|电池|电力|电网|氢能|核电|碳|"
    r"逆变器|组件|虚拟电厂|VPP|组串|跟踪|发电|充电"
)


def crawl() -> dict:
    html = fetch_html(BASE_URL)

    # detect_waf also catches ne21's tiny JS-redirect shell (len < 500 +
    # window.location.href)
    waf = detect_waf(html)
    if waf:
        return empty_feed(
            SOURCE,
            SOURCE_NAME,
            error=(
                f"{waf}. If this persists on GitHub Actions, use the "
                "Playwright workflow (crawlers/ne21_playwright.py)."
            ),
        )

    # Parse article-like links from the homepage. ne21 uses a variety of
    # URL shapes — we match any .html page with an energy-related title.
    pattern = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,100})</a>',
        re.IGNORECASE,
    )
    raw_matches = pattern.findall(html)

    seen: set[str] = set()
    articles: list[dict] = []

    for href, raw_title in raw_matches:
        title = clean_text(raw_title)
        if not title or not ENERGY_KEYWORDS.search(title):
            continue

        # Normalize to absolute URL
        if href.startswith("//"):
            url = f"https:{href}"
        elif href.startswith("/"):
            url = urljoin(BASE_URL, href)
        elif href.startswith("http"):
            url = href
        else:
            continue  # skip fragments like "#top", "javascript:", etc.

        if "ne21.com" not in url:
            continue
        # Must look like an article: .html / .htm / numeric path
        if not (url.endswith((".html", ".htm")) or re.search(r"/\d+[/.]?$", url)):
            continue
        if url in seen:
            continue
        seen.add(url)

        # Try to extract article id from URL
        m = re.search(r"(\d{4,})", url)
        article_id = m.group(1) if m else url[-20:]

        articles.append(
            {
                "id": f"ne21-{article_id}",
                "title": title,
                "url": url,
                "summary": "",
                "publishedAt": None,  # ne21 URLs don't carry dates
                "source": SOURCE,
            }
        )

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
