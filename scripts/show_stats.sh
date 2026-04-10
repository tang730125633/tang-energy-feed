#!/bin/bash
#
# show_stats.sh — print final feed statistics at the end of the crawl.
# Called from daily-crawl.yml's "Show final stats" step.
# Extracted to avoid inline YAML heredoc parsing issues.

set -uo pipefail

ls -la feed/
echo ""

python3 - << 'PY'
import json
import os

def safe_load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"  ({path} unreadable: {e})")
        return None

d = safe_load("feed/feed-digest.json")
if d:
    print("=== feed-digest.json ===")
    stats = d.get("stats", {})
    print(f"  articles:    {stats.get('totalArticles', 0)}")
    print(f"  by source:   {stats.get('bySource', {})}")
    print(f"  by province: {stats.get('byProvince', {})}")
    print(f"  copper:      {'yes' if d.get('copper') else 'NO'}")
    print(f"  errors:      {len(d.get('errors', []))}")

print()

ce = safe_load("feed/feed-central-energy.json")
if ce:
    print("=== feed-central-energy.json ===")
    stats = ce.get("stats", {})
    print(f"  articles:    {stats.get('totalArticles', 0)}")
    print(f"  by province: {stats.get('byProvince', {})}")
PY
