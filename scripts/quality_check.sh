#!/bin/bash
#
# quality_check.sh — Week 3 feature: validate feed-digest.json has
# enough articles and critical fields before committing.
#
# Called from daily-crawl.yml. Extracted to its own file to avoid YAML
# heredoc parsing issues (Python inside a `run: |` block confuses the
# GitHub Actions YAML parser).
#
# Exit codes:
#   0  = pass (enough articles + copper present)
#   42 = warning (low quality; caller should notify but keep going)
#   1  = hard failure (file missing / malformed)
#
# Usage:
#   bash scripts/quality_check.sh [path_to_feed_digest.json]
#
# Default path: feed/feed-digest.json

set -uo pipefail

FEED_PATH="${1:-feed/feed-digest.json}"

if [ ! -f "$FEED_PATH" ]; then
  echo "✗ Feed file not found: $FEED_PATH"
  exit 1
fi

python3 - "$FEED_PATH" << 'PY'
import json
import sys

feed_path = sys.argv[1]

try:
    with open(feed_path) as f:
        d = json.load(f)
except Exception as e:
    print(f"✗ Cannot parse {feed_path}: {e}")
    sys.exit(1)

total = d.get("stats", {}).get("totalArticles", 0)
has_copper = d.get("copper") is not None
errors = d.get("errors", [])
by_source = d.get("stats", {}).get("bySource", {})

print(f"articles={total}, copper={'yes' if has_copper else 'NO'}, errors={len(errors)}")
print(f"by source: {by_source}")

if errors:
    print("errors:")
    for e in errors:
        src = e.get("source", "?")
        first_err = (e.get("errors") or ["(none)"])[0]
        print(f"  - {src}: {first_err[:100]}")

# Thresholds
MIN_ARTICLES = 30

warnings = []
if total < MIN_ARTICLES:
    warnings.append(f"only {total} articles (< {MIN_ARTICLES} threshold)")
if not has_copper:
    warnings.append("copper price missing")

if warnings:
    print()
    print(f"⚠ Quality warnings: {'; '.join(warnings)}")
    sys.exit(42)

print()
print("✓ Quality check passed")
sys.exit(0)
PY
