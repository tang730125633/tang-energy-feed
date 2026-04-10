#!/bin/bash
#
# notify.sh — Week 3 feature: send failure / anomaly notifications to
# Slack / email when the crawl pipeline has problems.
#
# Configuration via environment variables (set as GitHub Secrets in the
# workflow):
#
#   SLACK_WEBHOOK_URL    Slack incoming-webhook URL
#   DISCORD_WEBHOOK_URL  Discord webhook (also Slack-compatible format)
#   LARK_WEBHOOK_URL     Feishu custom bot webhook URL (recommended for
#                        this project since you're already on Feishu)
#
# Any subset can be configured. Missing channels are silently skipped.
#
# Usage:
#   ./scripts/notify.sh "alert title" "message body"
#
# Exit codes:
#   0 = at least one channel delivered (or no channels configured)
#   1 = at least one channel failed
#
# This script is designed to never cause a workflow to fail — calling
# workflows should use `continue-on-error: true` to be safe.

set -uo pipefail  # NOT -e, we want to keep trying other channels on failure

TITLE="${1:-tang-energy-feed alert}"
BODY="${2:-(no message body)}"
TIMESTAMP="$(date -u +'%Y-%m-%d %H:%M UTC')"

any_failure=0
any_sent=0

# -----------------------------------------------------------------------------
# Slack webhook
# -----------------------------------------------------------------------------
if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
  echo "→ Sending to Slack..."
  payload=$(cat << JSON
{
  "text": "*${TITLE}*",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*${TITLE}*\n${BODY}\n\n_${TIMESTAMP}_"
      }
    }
  ]
}
JSON
)
  if curl -sS -X POST -H 'Content-type: application/json' \
       --data "$payload" "$SLACK_WEBHOOK_URL" > /dev/null; then
    echo "  ✓ Slack delivered"
    any_sent=1
  else
    echo "  ✗ Slack failed"
    any_failure=1
  fi
fi

# -----------------------------------------------------------------------------
# Discord webhook (uses Slack-compatible endpoint)
# -----------------------------------------------------------------------------
if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
  echo "→ Sending to Discord..."
  payload=$(cat << JSON
{
  "content": "**${TITLE}**\n${BODY}\n_${TIMESTAMP}_"
}
JSON
)
  if curl -sS -X POST -H 'Content-type: application/json' \
       --data "$payload" "$DISCORD_WEBHOOK_URL" > /dev/null; then
    echo "  ✓ Discord delivered"
    any_sent=1
  else
    echo "  ✗ Discord failed"
    any_failure=1
  fi
fi

# -----------------------------------------------------------------------------
# Feishu custom bot webhook
# Feishu expects a slightly different JSON shape.
# Recommended for this project since Tang is already on Feishu.
# -----------------------------------------------------------------------------
if [ -n "${LARK_WEBHOOK_URL:-}" ]; then
  echo "→ Sending to Feishu..."
  payload=$(cat << JSON
{
  "msg_type": "text",
  "content": {
    "text": "[${TITLE}] ${BODY} (${TIMESTAMP})"
  }
}
JSON
)
  if curl -sS -X POST -H 'Content-type: application/json' \
       --data "$payload" "$LARK_WEBHOOK_URL" > /dev/null; then
    echo "  ✓ Feishu delivered"
    any_sent=1
  else
    echo "  ✗ Feishu failed"
    any_failure=1
  fi
fi

if [ $any_sent -eq 0 ]; then
  echo "ℹ No notification channels configured — set SLACK_WEBHOOK_URL / DISCORD_WEBHOOK_URL / LARK_WEBHOOK_URL"
  exit 0  # not an error, just nothing to do
fi

exit $any_failure
