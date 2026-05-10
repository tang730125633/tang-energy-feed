#!/usr/bin/env python3
"""
Crawler for 新华社能源频道 (xinhuanet.com/energy/).

Strategy:
- Fetch the energy channel homepage (no WAF, stable CDN)
- Extract all <a href="/energy/YYYYMMDD/..."> links with Chinese anchor text
- Date is directly embedded in URL path: /energy/20260509/xxx/c.html
- Filter energy-related titles; deduplicate by URL
- Only include articles published within LOOKBACK_HOURS

Source reliability: Very high — Xinhua is the state newswire.
Content quality: Policy-first (NDRC, NEA official releases land here first).
Update frequency: 3-8 articles/day, every day including weekends.
"""

from __future__ import annotations

import datetime as dt
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
    within_lookback,
)

SOURCE = "xinhuanet.com"
SOURCE_NAME = "新华社能源频道"
BASE_URL = "https://www.xinhuanet.com/energy/"
LOOKBACK_HOURS = 72  # Xinhua updates 3-8 times/day; use wider window for weekends

# Words that strongly indicate energy industry content.
ENERGY_KEYWORDS = re.compile(
    r"能源|电力|电网|储能|风电|光伏|新能源|核电|氢能|碳|发电|"
    r"可再生|清洁|绿电|VPP|虚拟电厂|油气|天然气|煤炭|充电|算力|双碳"
)

# Navigation / boilerplate text to skip.
CHROME_KEYWORDS = re.compile(
    r"^(首页|更多|登录|注册|English|关于我们|版权|ICP|联系|专题|视频|图片|"
    r"评论|分享|收藏|打印|纠错|新华网|Xinhua)"
)


def extract_date_from_xinhua_url(url: str) -> str | None:
    """Parse YYYYMMDD from Xinhua energy URL paths like /energy/20260509/xxx."""
    m = re.search(r"/energy/(20\d{6})/", url)
    if not m:
        return None
    s = m.group(1)
    try:
        d = dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        return d.isoformat()
    except ValueError:
        return None


def crawl() -> dict:
    html = fetch_html(BASE_URL)

    waf = detect_waf(html)
    if waf:
        return empty_feed(SOURCE, SOURCE_NAME, error=f"WAF detected: {waf}")

    # Match links that reference the energy channel with a date path component.
    # Pattern: href="/energy/20XXXXXX/..." or full URL
    pattern = re.compile(
        r'<a[^>]+href="([^"]*(?:/energy/20\d{6}/)[^"]*)"[^>]*>([^<]{6,120})</a>',
        re.IGNORECASE,
    )
    raw_matches = pattern.findall(html)

    # Also catch links that appear without the /energy/ prefix (relative within
    # the page), just in case the site rewrites them.
    pattern2 = re.compile(
        r'href="(/energy/(20\d{6})/[^"]+)"[^>]*>\s*([^<]{6,120})',
        re.IGNORECASE,
    )
    raw_matches2 = [(m[0], m[2]) for m in pattern2.findall(html)]

    all_raw = raw_matches + raw_matches2

    seen_urls: set[str] = set()
    articles: list[dict] = []

    for href, raw_title in all_raw:
        title = clean_text(raw_title)
        if not title:
            continue
        if CHROME_KEYWORDS.match(title):
            continue
        # Most Xinhua energy articles are inherently energy-related, but
        # apply the keyword filter to avoid off-topic content (e.g. earthday
        # ecology articles that appear on the energy channel).
        if not ENERGY_KEYWORDS.search(title):
            continue

        # Normalize URL
        if href.startswith("//"):
            url = f"https:{href}"
        elif href.startswith("/"):
            url = f"https://www.xinhuanet.com{href}"
        elif href.startswith("http"):
            url = href
        else:
            continue

        # Only keep xinhuanet.com energy URLs
        if "xinhuanet.com" not in url:
            continue
        if "/energy/" not in url:
            continue
        # Must end in /c.html or similar article terminator
        if not (url.endswith(".html") or url.endswith(".htm")):
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        published_at = extract_date_from_xinhua_url(url)
        if not within_lookback(published_at, LOOKBACK_HOURS):
            continue

        # Build a stable article ID from the hash in the URL
        m = re.search(r"/energy/20\d{6}/([0-9a-f]{20,})/", url)
        article_id = m.group(1)[:12] if m else re.sub(r"[^a-zA-Z0-9]", "", url)[-12:]

        articles.append(
            {
                "id": f"xinhua-{article_id}",
                "title": title,
                "url": url,
                "summary": "",
                "publishedAt": published_at,
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
