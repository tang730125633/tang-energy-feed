#!/usr/bin/env python3
"""
Crawler for 中国电力网 (chinapower.org.cn).

Strategy:
- Fetch the homepage to collect all /detail/NNNNNN.html links
- Sort by article ID descending (higher = newer, sequential numbering)
- Fetch the top MAX_DETAIL_FETCH article pages to extract publish dates
- Filter to articles within LOOKBACK_HOURS; keep up to MAX_ARTICLES

Design notes:
- chinapower.org.cn has no WAF and is consistently accessible
- Article IDs are sequential integers; higher = more recent
- Dates are in <div class="date">YYYY-MM-DD</div> inside each article page
- Fetching individual pages is necessary because the homepage does not
  expose publish dates in its HTML
- We limit detail fetches to MAX_DETAIL_FETCH to stay well under GitHub
  Actions timeout. At ~0.5s/page that is ~10s total.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import time
import traceback

from common import (
    clean_text,
    detect_waf,
    emit,
    empty_feed,
    fetch_html,
    utc_now_iso,
    within_lookback,
)

SOURCE = "chinapower.org.cn"
SOURCE_NAME = "中国电力网"
BASE_URL = "https://www.chinapower.org.cn/"
LOOKBACK_HOURS = 48
MAX_DETAIL_FETCH = 20   # how many article pages to open for date extraction
MAX_ARTICLES = 30       # cap final article list

# Only consider articles whose ID is at least this (old pinned articles have low IDs).
# Raise this periodically — at ~20 articles/day, it grows ~600/month.
MIN_ARTICLE_ID = 440000

ENERGY_KEYWORDS = re.compile(
    r"电力|电网|能源|储能|风电|光伏|核电|可再生|新能源|发电|输电|"
    r"配电|绿电|碳|氢能|充电|算力|虚拟电厂|抽蓄|VPP|清洁|特高压|"
    r"火电|水电|煤炭|天然气|油气|双碳|分布式|微电网|需求响应"
)

CHROME_KEYWORDS = re.compile(
    r"^(首页|登录|注册|关于|联系|投稿|English|版权|ICP|主办|主管|"
    r"Copyright|更多|下载|订阅|搜索|导航|招聘|广告)"
)


def extract_article_date(html: str) -> str | None:
    """Return ISO date from chinapower article page HTML."""
    # Primary: <div class="date">2026-05-09</div>
    m = re.search(
        r'<div[^>]*class=["\']date["\'][^>]*>(202[3-6]-\d{2}-\d{2})</div>',
        html,
    )
    if m:
        try:
            return dt.date.fromisoformat(m.group(1)).isoformat()
        except ValueError:
            pass

    # Fallback: search full page for YYYY-MM-DD
    m2 = re.search(r"(202[3-6]-\d{2}-\d{2})", html)
    if m2:
        try:
            return dt.date.fromisoformat(m2.group(1)).isoformat()
        except ValueError:
            pass

    # Fallback 2: YYYY年MM月DD日
    m3 = re.search(r"(202[3-6])年(\d{1,2})月(\d{1,2})日", html)
    if m3:
        try:
            return dt.date(int(m3.group(1)), int(m3.group(2)), int(m3.group(3))).isoformat()
        except ValueError:
            pass

    return None


def crawl() -> dict:
    html = fetch_html(BASE_URL)

    waf = detect_waf(html)
    if waf:
        return empty_feed(SOURCE, SOURCE_NAME, error=f"WAF detected: {waf}")

    # Collect all /detail/NNN.html links
    href_pattern = re.compile(
        r'href="(?:https?://www\.chinapower\.org\.cn)?(/detail/(\d+)\.html)"',
        re.IGNORECASE,
    )
    all_ids_seen: dict[int, str] = {}
    for m in href_pattern.finditer(html):
        path, id_str = m.group(1), m.group(2)
        article_id = int(id_str)
        if article_id >= MIN_ARTICLE_ID:
            all_ids_seen[article_id] = f"https://www.chinapower.org.cn{path}"

    # Also collect associated titles (visible anchor text)
    title_pattern = re.compile(
        r'href="(?:https?://www\.chinapower\.org\.cn)?/detail/(\d+)\.html"[^>]*>\s*([^<]{4,100})',
        re.IGNORECASE,
    )
    id_to_title: dict[int, str] = {}
    for m in title_pattern.finditer(html):
        article_id = int(m.group(1))
        title = clean_text(m.group(2))
        if title and article_id and article_id not in id_to_title:
            id_to_title[article_id] = title

    candidates = sorted(all_ids_seen.keys(), reverse=True)[:MAX_DETAIL_FETCH]

    if not candidates:
        return empty_feed(
            SOURCE, SOURCE_NAME,
            error=f"No article IDs >= {MIN_ARTICLE_ID} found on homepage."
        )

    errors: list[str] = []
    articles: list[dict] = []

    for article_id in candidates:
        url = all_ids_seen[article_id]
        try:
            detail_html = fetch_html(url)
            published_at = extract_article_date(detail_html)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Failed to fetch {url}: {e}")
            published_at = None

        if not within_lookback(published_at, LOOKBACK_HOURS):
            # Once we hit an article clearly outside the window, stop fetching
            if published_at and published_at < (
                dt.date.today() - dt.timedelta(days=max(2, LOOKBACK_HOURS // 24) + 1)
            ).isoformat():
                break
            continue

        # Get title
        title = id_to_title.get(article_id)
        if not title:
            m = re.search(r"<h1[^>]*>([^<]{4,100})</h1>", detail_html, re.IGNORECASE)
            title = clean_text(m.group(1)) if m else ""
        if not title:
            continue
        if CHROME_KEYWORDS.match(title):
            continue
        if not ENERGY_KEYWORDS.search(title):
            continue

        articles.append(
            {
                "id": f"chinapower-{article_id}",
                "title": title,
                "url": url,
                "summary": "",
                "publishedAt": published_at,
                "source": SOURCE,
            }
        )

        if len(articles) >= MAX_ARTICLES:
            break

        time.sleep(0.3)

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
