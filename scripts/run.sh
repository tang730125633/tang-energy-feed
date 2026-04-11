#!/bin/bash
#
# run.sh — one-shot entrypoint for the full delivery workflow.
#
# TWO MODES (Tang decided this ~16:00):
#
# --production (default, used by launchd / cron):
#   Runs all 8 steps. Reads and writes .last-sent-date (idempotent daily),
#   reads archive/seen-urls.json (dedups URLs), writes 3 archive files
#   and updates seen-urls. This is the mode that makes Tang's daily
#   timeline consistent: launchd fires at 10:30 + 11:00, the first
#   successful run archives and the second is skipped.
#
# --test (used by humans in chat, via Skill):
#   Runs Steps 1-6. SKIPS Step 0 (.last-sent-date check), SKIPS dedup
#   filter (classifies against raw feed — can pick URLs already used),
#   and SKIPS Step 7 (archive). A test run can be repeated 10 times in
#   a row without polluting seen-urls.json or .last-sent-date. It still
#   REALLY sends to Feishu — Tang is approving the card visually, and
#   wants to see the actual rendered output in the group.
#
# Steps:
#   0. Already-sent-today check          [production only]
#   1. Load Config                        [always]
#   2. Fetch Feed                         [always]
#   3. Check Content                      [always]
#   4. Classify Candidates
#      └─ with dedup filter               [production only]
#      └─ without dedup filter (--no-dedup) [test]
#   5. AI Remix                           [always]
#   6. Build Card + Deliver               [always]
#   7. Archive                            [production only]
#
# DUAL-MODE DELIVERY (Step 6):
#   - LOCAL mode: uses lark-cli (if installed and LARK_APP_ID not set in env)
#   - CI mode:    uses scripts/send_lark.py (Python + stdlib, no lark-cli dep)
#
# Usage:
#   bash scripts/run.sh                   # defaults to --production
#   bash scripts/run.sh --production      # explicit; same as no args
#   bash scripts/run.sh --test            # human test mode (no archive)
#
# Exit codes:
#   0 = success (sent + archived in production, or sent in test)
#       OR already sent today (idempotent skip, production only)
#   1 = user error (bad config, missing API key)
#   2 = upstream failure (feed empty / LLM down) — safe to retry
#   3 = downstream failure (lark send failed) — safe to retry
#
# FORCING A RESEND IN PRODUCTION: delete .last-sent-date and re-run.
# Use with care — it re-sends and re-archives.

set -euo pipefail

# ---- parse mode flag ----
MODE="production"
for arg in "$@"; do
  case "$arg" in
    --test)       MODE="test" ;;
    --production) MODE="production" ;;
    *) echo "Unknown argument: $arg" >&2; echo "Usage: $0 [--test|--production]" >&2; exit 1 ;;
  esac
done

# Resolve this script's own directory (works even when called by launchd,
# which does NOT inherit the user's cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

CONFIG="${REPO_ROOT}/config.json"
LAST_SENT_FILE="${REPO_ROOT}/.last-sent-date"

# Working directory for intermediate JSON files
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
today_local() { date '+%Y-%m-%d'; }

echo "┌─────────────────────────────────────────────────────┐"
echo "│  Zero-Carbon Energy Daily Digest — $(timestamp)  │"
echo "│  Mode: $MODE$( [ "$MODE" = "test" ] && echo " (no archive, no .last-sent-date, no dedup)" || echo " (full pipeline: archive + dedup + .last-sent-date)" )"
echo "└─────────────────────────────────────────────────────┘"

# -----------------------------------------------------------------------------
# Step 0: Already-sent-today check (production only)
# -----------------------------------------------------------------------------
# In PRODUCTION mode, if today's digest has already been sent successfully,
# exit immediately. This is what makes the 10:30 + 11:00 double-trigger safe.
#
# In TEST mode, SKIP this check — humans may want to test multiple times
# per day without being blocked.
if [ "$MODE" = "production" ]; then
  echo ""
  echo "▸ Step 0/7: Already-sent-today check [production]"
  TODAY=$(today_local)
  if [ -f "$LAST_SENT_FILE" ]; then
    LAST_SENT=$(tr -d '[:space:]' < "$LAST_SENT_FILE")
    if [ "$LAST_SENT" = "$TODAY" ]; then
      echo "  ✓ Today's digest already sent ($LAST_SENT). Skipping (exit 0)."
      echo "  Hint: to force re-send, delete .last-sent-date and re-run."
      exit 0
    fi
    echo "  ℹ Last sent: $LAST_SENT (≠ today $TODAY) — proceeding"
  else
    echo "  ℹ First run — no .last-sent-date yet"
  fi
else
  echo ""
  echo "▸ Step 0/7: Skipped (test mode — no .last-sent-date check)"
fi

# -----------------------------------------------------------------------------
# Step 1: Load Config (validate it exists and has required fields)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 1/7: Load config"
if [ ! -f "$CONFIG" ]; then
  echo "✗ Missing config.json at $CONFIG" >&2
  echo "  Run: ./scripts/setup.sh" >&2
  echo "  Or copy config.example.json to config.json and edit it." >&2
  exit 1
fi

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

# Also extract model name from config for later use in archive step
MODEL_NAME=$(python3 -c "
import json
print(json.load(open('$CONFIG'))['ai']['model'])
")

echo "  ✓ Config OK, target chat_id = ${CHAT_ID:0:12}..., model = $MODEL_NAME"

# -----------------------------------------------------------------------------
# Step 2: Fetch Feed
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 2/7: Fetch feed from upstream"
python3 scripts/fetch_feed.py "$CONFIG" > "$TMP_DIR/feed.json" || {
  echo "✗ Fetch failed" >&2
  exit 2
}

# -----------------------------------------------------------------------------
# Step 3: Check Content (abort if feed is empty)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 3/7: Check content"
CONTENT_INFO=$(python3 -c "
import json
d = json.load(open('$TMP_DIR/feed.json'))
total = d.get('stats', {}).get('totalArticles', 0)
copper = d.get('copper') is not None
generated = d.get('generatedAt', '')
print(f'{total}|{copper}|{generated}')
")
TOTAL_ARTICLES="$(echo "$CONTENT_INFO" | cut -d'|' -f1)"
HAS_COPPER="$(echo "$CONTENT_INFO" | cut -d'|' -f2)"
FEED_GENERATED_AT="$(echo "$CONTENT_INFO" | cut -d'|' -f3)"

echo "  articles=$TOTAL_ARTICLES, copper=$HAS_COPPER, generatedAt=$FEED_GENERATED_AT"
if [ "$TOTAL_ARTICLES" -lt 10 ]; then
  echo "✗ Feed has only $TOTAL_ARTICLES articles (< 10). Upstream crawlers may be failing." >&2
  echo "  Check: https://github.com/tang730125633/tang-energy-feed/actions" >&2
  exit 2
fi

# -----------------------------------------------------------------------------
# Step 4: Classify Candidates
# -----------------------------------------------------------------------------
# In PRODUCTION: classify_candidates.py auto-loads archive/seen-urls.json
#                and drops already-used URLs from the candidate pools.
# In TEST:       pass --no-dedup so the AI sees the raw candidates — a
#                test run should be "what today's feed could produce right
#                now", not "what's left after the week's selections".
echo ""
if [ "$MODE" = "test" ]; then
  echo "▸ Step 4/7: Classify candidates [test — no dedup]"
  python3 scripts/classify_candidates.py --no-dedup "$TMP_DIR/feed.json" > "$TMP_DIR/candidates.json"
else
  echo "▸ Step 4/7: Classify candidates [production — with dedup]"
  python3 scripts/classify_candidates.py "$TMP_DIR/feed.json" > "$TMP_DIR/candidates.json"
fi

# -----------------------------------------------------------------------------
# Step 5: AI Remix (the only step that needs an LLM API key)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 5/7: AI remix"
python3 scripts/ai_remix.py "$CONFIG" "$TMP_DIR/candidates.json" > "$TMP_DIR/input.json" || {
  echo "✗ AI remix failed. Check LLM API key, quota, and model name." >&2
  exit 2
}

# -----------------------------------------------------------------------------
# Step 6: Build Card + Deliver (dual-mode)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Step 6/7: Build card + deliver"
python3 scripts/build_card.py "$TMP_DIR/input.json" > "$TMP_DIR/card.json"

MESSAGE_ID="unknown"

# Decide which sender to use:
#   CI mode:    LARK_APP_ID + LARK_APP_SECRET + FEISHU_CHAT_ID in env
#               → use scripts/send_lark.py (zero dep, stdlib only)
#   Local mode: lark-cli is installed and those env vars are NOT set
#               → use lark-cli (nicer local dev experience)
if [ -n "${LARK_APP_ID:-}" ] && [ -n "${LARK_APP_SECRET:-}" ] && [ -n "${FEISHU_CHAT_ID:-}" ]; then
  echo "  → CI mode: sending via scripts/send_lark.py (stdlib, zero dep)"
  python3 scripts/send_lark.py "$TMP_DIR/card.json" 2> "$TMP_DIR/send_stderr.log" || {
    echo "✗ send_lark.py failed" >&2
    cat "$TMP_DIR/send_stderr.log" >&2 2>/dev/null || true
    exit 3
  }
  # send_lark.py logs "message_id=om_xxx" to stderr; extract it
  MESSAGE_ID=$(grep -o "message_id=[^ ]*" "$TMP_DIR/send_stderr.log" | tail -1 | cut -d= -f2 || echo "unknown")
  cat "$TMP_DIR/send_stderr.log" >&2
  echo ""
  echo "  ✓ CI mode sent. message_id=$MESSAGE_ID"
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
  echo "  ✓ Local mode sent. message_id=$MESSAGE_ID"
else
  echo "✗ No sender available." >&2
  echo "  Local mode needs lark-cli installed (npm install -g @larksuite/cli)." >&2
  echo "  CI mode needs env vars: LARK_APP_ID, LARK_APP_SECRET, FEISHU_CHAT_ID." >&2
  exit 3
fi

# -----------------------------------------------------------------------------
# Step 7: Archive (production only)
# -----------------------------------------------------------------------------
# Archive is a BEST-EFFORT post-send step. If it fails, the message has
# already been delivered, so we don't return non-zero — we just log.
#
# In TEST mode, the archive step is SKIPPED entirely. Human test runs
# should not pollute the historical archive or the seen-urls dedup cache,
# because:
#   1. A human tester may run 5 tests in an hour — writing 5 archive files
#      with the same date would overwrite each other
#   2. Test URLs would get added to seen-urls.json and then be filtered out
#      from tomorrow's legitimate cron run — a test would "steal" content
#      from the production schedule
#
# Only the cron/launchd production run owns the archive.
if [ "$MODE" = "production" ]; then
  echo ""
  echo "▸ Step 7/7: Archive [production]"
  python3 scripts/archive.py \
    --input "$TMP_DIR/input.json" \
    --message-id "$MESSAGE_ID" \
    --chat-id "$CHAT_ID" \
    --feed-generated-at "$FEED_GENERATED_AT" \
    --feed-total-articles "$TOTAL_ARTICLES" \
    --model "$MODEL_NAME" || {
    echo "  ⚠ Archive step returned non-zero (WARN — message already delivered)" >&2
  }
else
  echo ""
  echo "▸ Step 7/7: Skipped (test mode — no archive, no seen-urls update, no .last-sent-date)"
fi

# -----------------------------------------------------------------------------
# Done.
# -----------------------------------------------------------------------------
echo ""
if [ "$MODE" = "production" ]; then
  echo "┌──────────────────────────────────────────────────┐"
  echo "│  ✅ Daily report delivered + archived              │"
  echo "│  message_id: $MESSAGE_ID"
  echo "│  timestamp:  $(timestamp)"
  echo "└──────────────────────────────────────────────────┘"
else
  echo "┌──────────────────────────────────────────────────┐"
  echo "│  ✅ Test report delivered (NOT archived)           │"
  echo "│  message_id: $MESSAGE_ID"
  echo "│  timestamp:  $(timestamp)"
  echo "│  note: no entry in archive/, seen-urls, or       │"
  echo "│        .last-sent-date — safe to run again        │"
  echo "└──────────────────────────────────────────────────┘"
fi
