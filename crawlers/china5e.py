#!/usr/bin/env python3
"""
Crawler for 中国能源网 (china5e.com).

Why this source?
- Updates 7 days/week (including weekends), unlike cpnn/nea which stop on
  Saturday/Sunday. This is the FALLBACK source that ensures we always have
  fresh articles.
- Structured HTML: <li><span>DATE</span>...<a href="URL" title="TITLE">
- No WAF, no JS challenge, direct fetch works.
- Covers: 储能, 风能, 光伏, 氢能, 石油, 天然气, 煤炭, 电力, 核电, 碳交易

Strategy:
- Fetch /news/ listing page
- Parse <li><span>DATE</span>...<a href="URL" title="TITLE"> pattern
- Deduplicate by URL, sort newest-first
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

SOURCE = "china5e.com"
SOURCE_NAME = "中国能源网"
BASE_URL = "https://www.china5e.com/news/"
# Also crawl homepage for top stories
HOME_URL = "https://www.china5e.com/"
LOOKBACK_HOURS = 72


# Matches: <li><span>2026-04-11</span>...<a href="URL" ... title="TITLE">
LI_PATTERN = re.compile(
    r"<li>\s*<span>(20\d{2}-\d{2}-\d{2})</span>"  # date in <span>
    r".*?"  # category link etc.
    r'<a\s+href="([^"]+news-\d+-\d+\.html)"'  # article URL
    r'[^>]*title="([^"]{4,120})"',  # title in title attr
    re.DOTALL,
)

# Broader pattern for homepage articles (different HTML structure)
HOME_PATTERN = re.compile(
    r'<a\s+href="(https?://www\.china5e\.com/news/news-\d+-\d+\.html)"'
    r'[^>]*title="([^"]{4,120})"',
    re.IGNORECASE,
)

ENERGY_KEYWORDS = re.compile(
    r"电力|电网|能源|储能|风电|光伏|核电|新能源|发电|碳|氢能|"
    r"充电|抽蓄|虚拟电厂|算力|输变电|特高压|煤|石油|天然气|"
    r"油气|风能|太阳能|地热|生物质|水电|调度|配电|输电|绿电"
)


def crawl() -> dict:
    articles: list[dict] = []
    seen_urls: set[str] = set()
    errors: list[str] = []

    # ---- Source 1: /news/ listing page (has dates) ----
    try:
        html = fetch_html(BASE_URL)
        waf = detect_waf(html)
        if waf:
            errors.append(f"/news/ WAF: {waf}")
        else:
            for date, href, title in LI_PATTERN.findall(html):
                title = clean_text(title)
                if not title:
                    continue
                url = urljoin(BASE_URL, href)
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Extract article ID from URL like news-1202412-1.html
                m = re.search(r"news-(\d+)-", url)
                aid = m.group(1) if m else url[-20:]

                articles.append(
                    {
                        "id": f"china5e-{aid}",
                        "title": title,
                        "url": url,
                        "summary": "",
                        "publishedAt": date,  # already YYYY-MM-DD
                        "source": SOURCE,
                    }
                )
    except Exception as e:
        errors.append(f"/news/ error: {type(e).__name__}: {e}")

    # ---- Source 2: homepage (may have different/newer articles) ----
    try:
        html2 = fetch_html(HOME_URL)
        waf2 = detect_waf(html2)
        if waf2:
            errors.append(f"homepage WAF: {waf2}")
        else:
            for href, title in HOME_PATTERN.findall(html2):
                title = clean_text(title)
                if not title or not ENERGY_KEYWORDS.search(title):
                    continue
                url = urljoin(HOME_URL, href)
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                m = re.search(r"news-(\d+)-", url)
                aid = m.group(1) if m else url[-20:]

                articles.append(
                    {
                        "id": f"china5e-{aid}",
                        "title": title,
                        "url": url,
                        "summary": "",
                        "publishedAt": None,  # homepage doesn't show date
                        "source": SOURCE,
                    }
                )
    except Exception as e:
        errors.append(f"homepage error: {type(e).__name__}: {e}")

    # Sort newest-first (None dates sink to bottom)
    articles.sort(
        key=lambda a: (a.get("publishedAt") or "0000-00-00"), reverse=True
    )

    return {
        "source": SOURCE,
        "sourceName": SOURCE_NAME,
        "generatedAt": utc_now_iso(),
        "lookbackHours": LOOKBACK_HOURS,
        "articles": articles,
        "stats": {"articleCount": len(articles)},
        "errors": errors,
    }


if __name__ == "__main__":
    try:
        emit(crawl())
    except Exception as e:  # noqa: BLE001
        emit(empty_feed(SOURCE, SOURCE_NAME, error=f"{type(e).__name__}: {e}"))
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(0)
