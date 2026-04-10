#!/usr/bin/env python3
"""
Playwright-based crawler for 北极星电力网 (bjx.com.cn).

bjx.com.cn sits behind Aliyun WAF which returns a JavaScript challenge
page. A plain `requests.get` can't bypass it. Playwright can, because it
runs a real Chromium that executes the challenge JS and sets the
`acw_sc__v2` cookie automatically.

⚠️ CI ENVIRONMENT CAVEAT: this script runs in GitHub Actions whose IPs
are based in the US. Chinese WAFs sometimes apply stricter rules to
overseas IPs. If this consistently fails, consider:
  1. Running the Playwright workflow from a self-hosted runner with
     Chinese-ISP IP
  2. Routing Playwright through a proxy
  3. Using a residential-IP service like ScrapingBee (paid)

This script is designed to NEVER raise. On failure it writes an empty
feed with an explicit error field, and the aggregate step continues.

Usage:
    python3 bjx_playwright.py > feed/feed-bjx.json
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timezone

SOURCE = "bjx.com.cn"
SOURCE_NAME = "北极星电力网"
BASE_URL = "https://news.bjx.com.cn/"
LOOKBACK_HOURS = 48
CHALLENGE_WAIT_MS = 5000  # how long to wait for the WAF challenge to resolve


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_feed(error: str = "") -> dict:
    return {
        "source": SOURCE,
        "sourceName": SOURCE_NAME,
        "generatedAt": utc_now_iso(),
        "lookbackHours": LOOKBACK_HOURS,
        "articles": [],
        "stats": {"articleCount": 0},
        "errors": [error] if error else [],
    }


def emit(feed: dict) -> None:
    sys.stdout.write(json.dumps(feed, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def extract_articles_from_html(html: str) -> list[dict]:
    """Parse the bjx news homepage once the WAF challenge has been solved."""
    # bjx article URLs look like:
    #   https://news.bjx.com.cn/html/20260410/1491512.shtml
    # or relative:
    #   /html/20260410/1491512.shtml
    pattern = re.compile(
        r'href="((?:https?://news\.bjx\.com\.cn)?/html/(\d{8})/(\d+)\.shtml)"[^>]*>([^<]{6,120})</',
        re.IGNORECASE,
    )
    matches = pattern.findall(html)

    seen: set[str] = set()
    articles: list[dict] = []
    for raw_url, date_str, article_id, title in matches:
        # Skip empty / too-short titles (often nav chrome)
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 6:
            continue

        # Normalize to absolute URL
        url = raw_url if raw_url.startswith("http") else f"https://news.bjx.com.cn{raw_url}"
        if url in seen:
            continue
        seen.add(url)

        # YYYYMMDD -> YYYY-MM-DD
        try:
            published_at = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except IndexError:
            published_at = None

        articles.append(
            {
                "id": f"bjx-{article_id}",
                "title": title,
                "url": url,
                "summary": "",
                "publishedAt": published_at,
                "source": SOURCE,
            }
        )

    # Sort newest-first by published date when available
    articles.sort(key=lambda a: (a["publishedAt"] or "0000-00-00"), reverse=True)
    return articles


def crawl_with_playwright() -> dict:
    """Use Playwright to fetch bjx, letting Chromium solve the WAF challenge."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return empty_feed(
            "playwright not installed. This script must be run with "
            "playwright installed (see crawlers/requirements-playwright.txt)."
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = context.new_page()

        try:
            # First navigation: we expect the WAF challenge page. Chromium
            # will execute the JS, set acw_sc__v2 cookie, and reload.
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")

            # Give the challenge some time to resolve
            page.wait_for_timeout(CHALLENGE_WAIT_MS)

            # Re-fetch after challenge has (hopefully) been solved
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            html = page.content()
        except Exception as e:  # noqa: BLE001
            browser.close()
            return empty_feed(f"Playwright navigation failed: {e}")

        browser.close()

    # If the challenge is still in the HTML, we failed to bypass
    if "aliyunwaf" in html[:3000].lower() or "acw_sc__v2" in html[:3000]:
        return empty_feed(
            "Aliyun WAF challenge not resolved after 7 seconds of JS execution. "
            "Consider increasing CHALLENGE_WAIT_MS, using a proxy, or a "
            "self-hosted runner with China-ISP IP."
        )

    articles = extract_articles_from_html(html)
    if not articles:
        return empty_feed(
            "WAF bypassed but parser found 0 articles. "
            "The homepage HTML structure may have changed — inspect the HTML."
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
        emit(crawl_with_playwright())
    except Exception as e:  # noqa: BLE001
        emit(empty_feed(f"{type(e).__name__}: {e}"))
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(0)
