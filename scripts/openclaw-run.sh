#!/bin/bash
#
# openclaw-run.sh — single-command entrypoint for OpenClaw cron on 戴总's Mac mini.
#
# This is the script OpenClaw should schedule. It does three things:
#
#   1. git pull — auto-sync the latest code from main branch. This means
#      Tang can git push updates from his own laptop and 戴总's OpenClaw
#      will pick them up on the NEXT scheduled run. Zero remote editing.
#
#   2. Verify required environment variables are present.
#
#   3. Call scripts/run.sh which does the full 6-step delivery workflow
#      (fetch → classify → Gemini remix → build card → lark-cli send).
#
# OpenClaw cron setup (on 戴总's Mac mini):
#
#     Cron: 30 10 * * *          # every day at 10:30 local time
#     Command: /path/to/tang-energy-feed/scripts/openclaw-run.sh
#     Working dir: (doesn't matter — script resolves its own path)
#     Environment: GEMINI_API_KEY, LARK_APP_ID, LARK_APP_SECRET, FEISHU_CHAT_ID
#
# Exit codes (propagated from run.sh):
#   0 = report sent successfully
#   1 = config / credential error
#   2 = upstream failure (feed empty / LLM down)
#   3 = downstream failure (lark send failed)

set -uo pipefail  # NOT -e — we handle errors ourselves so OpenClaw gets
                  # a meaningful exit code even when git pull fails.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

timestamp() { date '+%Y-%m-%d %H:%M:%S %Z'; }

echo "══════════════════════════════════════════════════════"
echo "  OpenClaw-triggered run — $(timestamp)"
echo "══════════════════════════════════════════════════════"

# -----------------------------------------------------------------------------
# Step 0: Sync latest code from GitHub
# -----------------------------------------------------------------------------
echo ""
echo "▸ Syncing with GitHub (git pull)"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Stash any local changes (shouldn't happen on 戴总's machine, but be safe)
  if ! git diff --quiet HEAD 2>/dev/null; then
    echo "  ⚠ Local changes detected — stashing before pull"
    git stash push -q -m "openclaw-autostash-$(date +%s)" || true
  fi

  if git pull --rebase --quiet origin main 2>&1; then
    HEAD_SHA=$(git rev-parse --short HEAD)
    echo "  ✓ Pulled successfully. HEAD is now at $HEAD_SHA"
  else
    echo "  ⚠ git pull failed — continuing with local version"
    # Don't abort. Running with stale code is better than not running at all.
  fi
else
  echo "  ⚠ Not a git repo — skipping pull"
fi

# -----------------------------------------------------------------------------
# Step 1: Sanity-check environment variables
# -----------------------------------------------------------------------------
echo ""
echo "▸ Checking environment"
missing=""
for var in GEMINI_API_KEY LARK_APP_ID LARK_APP_SECRET FEISHU_CHAT_ID; do
  if [ -z "${!var:-}" ]; then
    missing="$missing $var"
  fi
done

if [ -n "$missing" ]; then
  echo "  ✗ Missing environment variables:$missing"
  echo ""
  echo "  OpenClaw should pass these as env vars when triggering this script."
  echo "  Example OpenClaw cron environment block:"
  echo ""
  echo "      GEMINI_API_KEY=AIza..."
  echo "      LARK_APP_ID=cli_..."
  echo "      LARK_APP_SECRET=..."
  echo "      FEISHU_CHAT_ID=oc_..."
  exit 1
fi
echo "  ✓ All 4 required env vars present"

# -----------------------------------------------------------------------------
# Step 2: Ensure config.json exists (generated from env vars for OpenClaw mode)
# -----------------------------------------------------------------------------
echo ""
echo "▸ Generating ephemeral config.json from env vars"
cat > config.json << EOF
{
  "feed_url": "https://raw.githubusercontent.com/tang730125633/tang-energy-feed/main/feed/feed-digest.json",
  "feishu": {
    "chat_id": "$FEISHU_CHAT_ID",
    "identity": "bot"
  },
  "ai": {
    "provider": "gemini",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "model": "gemini-3-pro-preview",
    "api_key_env": "GEMINI_API_KEY",
    "temperature": 0.3,
    "response_format_json": true
  },
  "lookback_hours": 48
}
EOF
echo "  ✓ config.json written (model: gemini-3-pro-preview)"

# -----------------------------------------------------------------------------
# Step 3: Delegate to run.sh
# -----------------------------------------------------------------------------
echo ""
echo "▸ Delegating to scripts/run.sh"
echo ""

bash scripts/run.sh
run_exit=$?

# -----------------------------------------------------------------------------
# Cleanup: remove config.json (defence in depth — contains chat_id)
# -----------------------------------------------------------------------------
rm -f config.json

echo ""
echo "══════════════════════════════════════════════════════"
if [ $run_exit -eq 0 ]; then
  echo "  ✅ Completed successfully — $(timestamp)"
else
  echo "  ✗ Failed with exit code $run_exit — $(timestamp)"
fi
echo "══════════════════════════════════════════════════════"

exit $run_exit
