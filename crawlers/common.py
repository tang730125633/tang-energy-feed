"""
Shared utilities for all crawlers.

Design principles (learned from follow-builders):
1. **Never raise** — every crawler outputs a valid JSON even on error.
   The aggregate step can then see which sources failed without crashing.
2. **Tagged output** — every feed JSON is self-describing: who produced it,
   when, how many articles, and what errors (if any) happened.
3. **No credentials** — crawlers only hit public pages. Never put API keys
   or tokens in this repo.
4. **Retry-friendly** — transient 404/5xx is common for Chinese news sites;
   fetch_html retries a couple of times before giving up.
"""

from __future__ import annotations

import datetime as dt
import html as html_module
import json
import re
import sys
import time
from typing import Any

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}


def utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def fetch_html(url: str, timeout: int = 20, retries: int = 2) -> str:
    """Fetch a URL and return decoded HTML.

    Retries on transient failures (404, 429, 5xx) up to `retries` times with
    exponential backoff. Raises requests.HTTPError on final failure.

    Most Chinese news sites serve GB2312/GBK — requests' auto-detection
    handles this via apparent_encoding, but we force UTF-8 first and
    fall back only if we see replacement characters.
    """
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url,
                headers={**DEFAULT_HEADERS, "Referer": url},
                timeout=timeout,
            )
            # Transient statuses worth retrying
            if resp.status_code in (404, 429, 500, 502, 503, 504):
                if attempt < retries:
                    backoff = 2 ** attempt  # 1s, 2s, 4s
                    print(
                        f"  ⏳ {url}: HTTP {resp.status_code}, "
                        f"retrying in {backoff}s (attempt {attempt + 1}/{retries + 1})",
                        file=sys.stderr,
                    )
                    time.sleep(backoff)
                    continue
            resp.raise_for_status()

            # Try UTF-8 first; if that fails, let requests auto-detect
            resp.encoding = "utf-8"
            text = resp.text
            if "\ufffd" in text[:2000]:
                resp.encoding = resp.apparent_encoding
                text = resp.text
            return text

        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
            if attempt < retries:
                backoff = 2 ** attempt
                print(
                    f"  ⏳ {url}: {type(e).__name__}, retrying in {backoff}s",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                continue
            raise

    # Shouldn't reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError(f"fetch_html exhausted retries for {url}")


def detect_waf(html: str) -> str | None:
    """Detect common Chinese CDN WAF challenge pages.

    Returns a short reason string if blocked, or None if the HTML looks
    like real content.
    """
    markers = [
        ("aliyunwaf", "Aliyun WAF JS challenge"),
        ("acw_sc__v2", "Aliyun Sec Cookie challenge"),
        ("cf-browser-verification", "Cloudflare browser challenge"),
        ("__cf_chl_", "Cloudflare bot challenge"),
    ]
    head = html[:3000].lower()
    for marker, reason in markers:
        if marker in head:
            return reason

    # ne21-style JS redirect shell (tiny HTML with window.location.href)
    if len(html) < 500 and "window.location.href" in html:
        return "JS redirect challenge (small shell page)"

    return None


def clean_text(s: str) -> str:
    """Unescape HTML entities and collapse whitespace."""
    s = html_module.unescape(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def extract_date_from_url(url: str) -> str | None:
    """Parse YYYYMMDD from URLs like t20260410_xxx.html or /html/20260410/xxx."""
    m = re.search(r"(20\d{6})", url)
    if not m:
        return None
    s = m.group(1)
    try:
        d = dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        return d.isoformat()
    except ValueError:
        return None


def within_lookback(iso_date: str | None, lookback_hours: int) -> bool:
    """Return True if iso_date is within the lookback window."""
    if not iso_date:
        return True  # keep items with unknown date — better than dropping
    try:
        d = dt.date.fromisoformat(iso_date)
    except ValueError:
        return True
    return d >= (dt.date.today() - dt.timedelta(days=max(1, lookback_hours // 24)))


def emit(feed: dict[str, Any]) -> None:
    """Write feed JSON to stdout. Always prints a valid JSON object."""
    sys.stdout.write(json.dumps(feed, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def empty_feed(source: str, source_name: str, error: str = "") -> dict[str, Any]:
    """Construct an empty-but-valid feed object for failure cases."""
    return {
        "source": source,
        "sourceName": source_name,
        "generatedAt": utc_now_iso(),
        "lookbackHours": 48,
        "articles": [],
        "stats": {"articleCount": 0},
        "errors": [error] if error else [],
    }
