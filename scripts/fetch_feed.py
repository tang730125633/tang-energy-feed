#!/usr/bin/env python3
"""
fetch_feed.py — Download the tang-energy-feed digest JSON.

Reads feed_url from config.json, downloads the JSON, validates it has
the expected shape, and writes it to stdout. Supports both remote
(https://) and local file paths (useful for offline testing).

Usage:
    python3 fetch_feed.py <config.json> > /tmp/feed.json
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fetch(url: str, timeout: int = 30) -> dict:
    """Fetch the feed from a URL or local file path.

    Local paths (relative or absolute, or file://) are read directly.
    https:// URLs go through urllib with a realistic User-Agent.
    """
    if url.startswith(("http://", "https://")):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
        return json.loads(raw)

    # Treat as local file path (strip file:// if present)
    if url.startswith("file://"):
        url = url[len("file://") :]
    with Path(url).open(encoding="utf-8") as f:
        return json.load(f)


def validate(feed: dict) -> None:
    """Check the feed has the shape we expect.

    If the upstream tang-energy-feed schema changes, this validator
    should be updated in lockstep with references/data-contract.md.
    """
    required_top = {"generatedAt", "sources", "articles", "stats"}
    missing = required_top - feed.keys()
    if missing:
        raise ValueError(f"Feed missing top-level fields: {sorted(missing)}")

    if not isinstance(feed["articles"], list):
        raise ValueError("Feed 'articles' must be a list")

    if not feed["articles"]:
        print(
            "Warning: feed has zero articles. Upstream crawlers may have "
            "failed today. Check the feed's 'errors' field:",
            file=sys.stderr,
        )
        print(json.dumps(feed.get("errors", []), ensure_ascii=False, indent=2),
              file=sys.stderr)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 fetch_feed.py <config.json>", file=sys.stderr)
        return 2

    config_path = Path(sys.argv[1])
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 2

    config = load_config(config_path)
    url = config.get("feed_url")
    if not url:
        print("config.json missing 'feed_url'", file=sys.stderr)
        return 2

    try:
        feed = fetch(url)
    except urllib.error.HTTPError as e:
        print(f"HTTP error fetching feed: {e.code} {e.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Network error fetching feed: {e.reason}", file=sys.stderr)
        print(
            "Hint: if you're in mainland China and raw.githubusercontent.com "
            "is slow, try a GitHub CDN mirror or set https_proxy.",
            file=sys.stderr,
        )
        return 1
    except json.JSONDecodeError as e:
        print(f"Feed is not valid JSON: {e}", file=sys.stderr)
        return 1

    try:
        validate(feed)
    except ValueError as e:
        print(f"Feed validation failed: {e}", file=sys.stderr)
        return 1

    # Write to stdout (downstream scripts pipe from here)
    sys.stdout.write(json.dumps(feed, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")

    # Brief summary to stderr so the caller knows what was fetched
    print(
        f"✓ Fetched feed: {feed['stats'].get('totalArticles', 0)} articles, "
        f"copper={'yes' if feed.get('copper') else 'no'}, "
        f"generated at {feed.get('generatedAt', 'unknown')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
