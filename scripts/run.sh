#!/bin/bash
#
# run.sh — one-shot entrypoint for the full delivery workflow.
#
# This script runs the 6-step Content Delivery Workflow:
#   1. Load Config
#   2. Fetch Feed
#   3. Check Content (abort if feed is empty)
#   4. Classify Candidates
#   5. AI Remix
#   6. Build Card + Deliver
#
# Called by launchd/cron at 10:30 daily, or manually for testing.
#
# DUAL-MODE DELIVERY (Step 6):
#   - LOCAL mode: uses lark-cli (if installed and LARK_APP_ID not set in env)
#   - CI mode:    uses scripts/send_lark.py (Python + stdlib, no lark-cli dep)
#                 Triggered when LARK_APP_ID + LARK_APP_SECRET + FEISHU_CHAT_ID
#                 are all set in the environment (typically via GitHub secrets).
#
# Exit codes:
#   0 = success (report sent)
#   1 = user error (bad config, missing API key)
#   2 = upstream failure (feed empty / LLM down)
#   3 = downstream failure (lark send failed)

set -euo pipefail

# Resolve this script's own directory (works even when called by launchd,
# which does NOT inherit the user's cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

CONFIG="${REPO_ROOT}/config.json"
if [ ! -f "$CONFIG" ]; then
  echo "✗ Missing config.json at $CONFIG" >&2
  echo "  Run: ./scripts/setup.sh" >&2
  echo "  Or copy config.example.json to config.json and edit it." >&2
  exit 1
fi

# Working directory for intermediate JSON files
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

echo "┌────────────────────────────────────────────────┐"
echo "│  Zero-Carbon Energy Daily Digest — $(timestamp) │"
echo "└────────────────────────────────────────────────┘"

# -----------------------------------------------------------------------------
# Step 1: Load Config (validate it exists and has required fields)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 1/6: Load config"
CHAT_ID=$(python3 -c "
import json, sys
try:
    c = json.load(open('$CONFIG'))
    assert c['feed_url'], 'feed_url missing'
    assert c['feishu']['chat_id'], 'feishu.chat_id missing'
    assert c['ai']['model'], 'ai.model missing'
    assert c['ai']['base_url'], 'ai.base_url missing'
    print(c['feishu']['chat_id'])
except Exception as e:
    print(f'config.json invalid: {e}', file=sys.stderr)
    sys.exit(1)
") || { echo "✗ Config validation failed" >&2; exit 1; }

if [[ "$CHAT_ID" == *"REPLACE"* ]]; then
  echo "✗ feishu.chat_id is still a placeholder. Edit config.json." >&2
  exit 1
fi
echo "  ✓ Config OK, target chat_id = ${CHAT_ID:0:12}..."

# -----------------------------------------------------------------------------
# Step 2: Fetch Feed
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 2/6: Fetch feed from upstream"
python3 scripts/fetch_feed.py "$CONFIG" > "$TMP_DIR/feed.json" || {
  echo "✗ Fetch failed" >&2
  exit 2
}

# -----------------------------------------------------------------------------
# Step 3: Check Content (abort if feed is empty)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 3/6: Check content"
CONTENT_OK=$(python3 -c "
import json
d = json.load(open('$TMP_DIR/feed.json'))
total = d.get('stats', {}).get('totalArticles', 0)
copper = d.get('copper') is not None
print(f'{total}:{copper}')
")
TOTAL_ARTICLES="${CONTENT_OK%:*}"
HAS_COPPER="${CONTENT_OK#*:}"
echo "  articles=$TOTAL_ARTICLES, copper=$HAS_COPPER"
if [ "$TOTAL_ARTICLES" -lt 10 ]; then
  echo "✗ Feed has only $TOTAL_ARTICLES articles (< 10). Upstream crawlers may be failing." >&2
  echo "  Check: https://github.com/tang730125633/tang-energy-feed/actions" >&2
  exit 2
fi

# -----------------------------------------------------------------------------
# Step 4: Classify Candidates
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 4/6: Classify candidates"
python3 scripts/classify_candidates.py "$TMP_DIR/feed.json" > "$TMP_DIR/candidates.json"

# -----------------------------------------------------------------------------
# Step 5: AI Remix (the only step that needs an LLM API key)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 5/6: AI remix"
python3 scripts/ai_remix.py "$CONFIG" "$TMP_DIR/candidates.json" > "$TMP_DIR/input.json" || {
  echo "✗ AI remix failed. Check LLM API key, quota, and model name." >&2
  exit 2
}

# -----------------------------------------------------------------------------
# Step 6: Build Card + Deliver (dual-mode)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 6/6: Build card + deliver"
python3 scripts/build_card.py "$TMP_DIR/input.json" > "$TMP_DIR/card.json"

# Decide which sender to use:
#   CI mode:    LARK_APP_ID + LARK_APP_SECRET + FEISHU_CHAT_ID in env
#               → use scripts/send_lark.py (zero dep, stdlib only)
#   Local mode: lark-cli is installed and those env vars are NOT set
#               → use lark-cli (nicer local dev experience)
if [ -n "${LARK_APP_ID:-}" ] && [ -n "${LARK_APP_SECRET:-}" ] && [ -n "${FEISHU_CHAT_ID:-}" ]; then
  echo "  → CI mode: sending via scripts/send_lark.py (stdlib, zero dep)"
  python3 scripts/send_lark.py "$TMP_DIR/card.json" || {
    echo "✗ send_lark.py failed" >&2
    exit 3
  }
  echo ""
  echo "┌────────────────────────────────────────────────┐"
  echo "│  ✅ Daily report delivered (CI mode)            │"
  echo "│  timestamp:  $(timestamp)"
  echo "└────────────────────────────────────────────────┘"
elif command -v lark-cli >/dev/null 2>&1; then
  echo "  → Local mode: sending via lark-cli"
  lark-cli im +messages-send \
    --chat-id "$CHAT_ID" \
    --as bot \
    --msg-type interactive \
    --content "$(cat "$TMP_DIR/card.json")" > "$TMP_DIR/send_result.json" || {
    echo "✗ lark-cli send failed" >&2
    cat "$TMP_DIR/send_result.json" >&2 2>/dev/null || true
    exit 3
  }

  MESSAGE_ID=$(python3 -c "
import json
try:
    d = json.load(open('$TMP_DIR/send_result.json'))
    print(d['data']['message_id'])
except Exception:
    print('unknown')
")

  echo ""
  echo "┌────────────────────────────────────────────────┐"
  echo "│  ✅ Daily report delivered (Local mode)         │"
  echo "│  message_id: $MESSAGE_ID"
  echo "│  timestamp:  $(timestamp)"
  echo "└────────────────────────────────────────────────┘"
else
  echo "✗ No sender available." >&2
  echo "  Local mode needs lark-cli installed (npm install -g @larksuite/cli)." >&2
  echo "  CI mode needs env vars: LARK_APP_ID, LARK_APP_SECRET, FEISHU_CHAT_ID." >&2
  exit 3
fi
