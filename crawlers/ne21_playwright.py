#!/usr/bin/env python3
"""
Playwright-based crawler for 世纪新能源网 (ne21.com).

ne21.com uses a JavaScript redirect-based anti-bot challenge. A plain
`requests.get` is served a tiny HTML page with:

    <script> window.location.href ="/"; </script>

Playwright bypasses this because Chromium actually executes the JS
and navigates to the real page.

Similar to bjx_playwright.py — runs in the standalone
.github/workflows/bjx-crawl.yml (which could be renamed to
playwright-crawl.yml since it now handles multiple JS-challenge sources).

Usage:
    python3 ne21_playwright.py > feed/feed-ne21.json
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timezone

SOURCE = "ne21.com"
SOURCE_NAME = "世纪新能源网"
BASE_URL = "https://www.ne21.com/"
LOOKBACK_HOURS = 48
CHALLENGE_WAIT_MS = 5000

ENERGY_KEYWORDS = re.compile(
    r"新能源|光伏|风电|储能|电力|电网|氢能|核电|碳|"
    r"逆变器|组件|电池|虚拟电厂|VPP"
)


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
    """Parse the ne21 homepage once the JS redirect has resolved."""
    # ne21 article URLs have varying shapes — look for anything with
    # a numeric ID path ending in .html
    pattern = re.compile(
        r'<a[^>]+href="([^"]*(?:news|article|html)[^"]*\.html?)"[^>]*>([^<]{6,100})</a>',
        re.IGNORECASE,
    )
    matches = pattern.findall(html)

    seen: set[str] = set()
    articles: list[dict] = []

    for href, raw_title in matches:
        title = re.sub(r"\s+", " ", raw_title).strip()
        if not title or not ENERGY_KEYWORDS.search(title):
            continue

        # Normalize URL
        if href.startswith("//"):
            url = f"https:{href}"
        elif href.startswith("/"):
            url = f"https://www.ne21.com{href}"
        elif href.startswith("http"):
            url = href
        else:
            url = f"https://www.ne21.com/{href.lstrip('./')}"

        if "ne21.com" not in url:
            continue
        if url in seen:
            continue
        seen.add(url)

        # Extract article ID from URL as best we can
        m = re.search(r"(\d+)\.html?", url)
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

    return articles


def crawl_with_playwright() -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return empty_feed(
            "playwright not installed. See crawlers/requirements-playwright.txt"
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
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(CHALLENGE_WAIT_MS)
            # If the JS redirect fired, we're now on the real homepage
            html = page.content()
        except Exception as e:  # noqa: BLE001
            browser.close()
            return empty_feed(f"Playwright navigation failed: {e}")

        browser.close()

    # Still the challenge shell?
    if len(html) < 1000 or "window.location.href" in html[:500]:
        return empty_feed("JS redirect challenge not resolved after Playwright wait")

    articles = extract_articles_from_html(html)
    if not articles:
        return empty_feed(
            "Challenge bypassed but parser found 0 articles. "
            "ne21 HTML structure may have changed."
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
