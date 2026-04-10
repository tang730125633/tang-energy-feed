#!/usr/bin/env python3
"""
Crawler for 北极星电力网 (bjx.com.cn).

⚠️ KNOWN LIMITATION (2026-04-11):
bjx.com.cn is behind Aliyun WAF which returns a JavaScript challenge page
(`aliyunwaf` / `acw_sc__v2`). A plain `requests.get` will never get past it.

To scrape bjx we need one of:
  1. A headless browser (playwright/selenium) that can run the JS challenge
     and set the `acw_sc__v2` cookie
  2. A third-party anti-WAF service (not recommended — adds a paid dependency)
  3. Find an RSS feed or mobile API that doesn't go through the WAF

**Day 1 status**: this crawler DETECTS the WAF and writes an empty-but-valid
feed with an explicit error field. The aggregate step will continue with
the other sources (cpnn, nea). This is a conscious trade-off: don't block
the pipeline on a hard source.

**Day 2+ TODO**: implement a playwright-based path. Install playwright in
the GitHub Actions workflow and use it ONLY for bjx:

    pip install playwright
    playwright install chromium
    # then use playwright.sync_api to fetch the page after JS execution
"""

from __future__ import annotations

import sys
import traceback

from common import (
    detect_waf,
    emit,
    empty_feed,
    fetch_html,
)

SOURCE = "bjx.com.cn"
SOURCE_NAME = "北极星电力网"
BASE_URL = "https://news.bjx.com.cn/"
LOOKBACK_HOURS = 48


def crawl() -> dict:
    html = fetch_html(BASE_URL)
    waf = detect_waf(html)
    if waf:
        # This is the expected path for Day 1.
        return empty_feed(
            SOURCE,
            SOURCE_NAME,
            error=(
                f"{waf}. Day 1 cannot bypass this. "
                "TODO: add playwright-based scraper in crawlers/bjx_playwright.py"
            ),
        )

    # If WAF is somehow absent (e.g. they disabled it), fall back to a
    # generic link extraction — untested.
    return empty_feed(
        SOURCE,
        SOURCE_NAME,
        error="WAF absent but no parser implemented yet; see TODO at top of file",
    )


if __name__ == "__main__":
    try:
        emit(crawl())
    except Exception as e:  # noqa: BLE001
        emit(empty_feed(SOURCE, SOURCE_NAME, error=f"{type(e).__name__}: {e}"))
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(0)
