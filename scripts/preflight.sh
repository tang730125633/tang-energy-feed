#!/bin/bash
#
# preflight.sh — pre-production readiness check
#
# Run this on the target machine BEFORE the scheduled 10:30 run to verify
# that every link in the chain is healthy. This script is READ-ONLY: it
# never sends messages, never writes files except /tmp/*, never mutates
# state, never contacts the LLM API.
#
# Usage:
#   cd ~/code/tang-energy-feed && git pull && bash scripts/preflight.sh
#
# Exit codes:
#   0 = all green (safe to wait for cron)
#   1 = critical failure (fix before 10:30 or cron will fail)
#   2 = warnings only (review, may still work)

set -u

# ----- Colors -----
if [ -t 1 ]; then
  GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"
  BLUE="\033[34m"; DIM="\033[2m"; BOLD="\033[1m"; RESET="\033[0m"
else
  GREEN=""; YELLOW=""; RED=""; BLUE=""; DIM=""; BOLD=""; RESET=""
fi

PASSED=0; WARNS=0; FAILED=0

pass()   { printf "  ${GREEN}✓${RESET}  %s\n" "$1"; PASSED=$((PASSED+1)); }
warn()   { printf "  ${YELLOW}⚠${RESET}  %s\n" "$1"; WARNS=$((WARNS+1)); }
fail()   { printf "  ${RED}✗${RESET}  %s\n" "$1"; FAILED=$((FAILED+1)); }
info()   { printf "  ${DIM}·${RESET}  %s\n" "$1"; }
header() { printf "\n${BLUE}${BOLD}━━━ %s ━━━${RESET}\n" "$1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO"

printf "\n"
printf "┌──────────────────────────────────────────────────────┐\n"
printf "│  tang-energy-feed preflight — ${BOLD}%s${RESET}  │\n" "$(date '+%Y-%m-%d %H:%M:%S')"
printf "└──────────────────────────────────────────────────────┘\n"

# ════════════════════════════════════════════════════════════
header "1. System time & timezone"
# ════════════════════════════════════════════════════════════

info "Now: $(date '+%Y-%m-%d %H:%M:%S %Z %z')"
UTC_OFFSET="$(date +%z)"
if [ "$UTC_OFFSET" = "+0800" ]; then
  pass "Timezone is UTC+8 (cron 10:30 = Beijing 10:30)"
else
  warn "Timezone is $UTC_OFFSET (not +0800) — confirm cron's 10:30 is Beijing time"
fi

info "Uptime: $(uptime | sed 's/^ *//' | cut -d',' -f1-2)"

# ════════════════════════════════════════════════════════════
header "2. Repository state"
# ════════════════════════════════════════════════════════════

if [ -d "$REPO/.git" ]; then
  HEAD_SHA="$(git rev-parse --short HEAD)"
  HEAD_MSG="$(git log -1 --format='%s')"
  pass "Repo: $REPO"
  info "HEAD: $HEAD_SHA — $HEAD_MSG"

  if git fetch --quiet origin main 2>/dev/null; then
    BEHIND="$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)"
    if [ "$BEHIND" = "0" ]; then
      pass "Up to date with origin/main"
    else
      warn "$BEHIND commit(s) behind origin/main — run: git pull --rebase origin main"
    fi
  else
    info "Could not fetch origin/main (network? proxy?)"
  fi
else
  fail "Not a git repo: $REPO"
fi

# ════════════════════════════════════════════════════════════
header "3. config.json"
# ════════════════════════════════════════════════════════════

if [ -f "$REPO/config.json" ]; then
  CFG_OUT="$(python3 - << 'PY'
import json, sys
try:
    c = json.load(open('config.json'))
except Exception as e:
    print('parse_error|' + str(e)); sys.exit()

missing = []
for path in ['feed_url',
             'feishu.chat_id', 'feishu.identity',
             'ai.base_url', 'ai.model', 'ai.api_key_env']:
    cur = c
    for part in path.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            cur = None; break
    if not cur:
        missing.append(path)
if missing:
    print('missing|' + ','.join(missing)); sys.exit()

if c['feishu']['identity'] != 'bot':
    print('bad_identity|' + c['feishu']['identity']); sys.exit()
if 'REPLACE' in c['feishu']['chat_id']:
    print('placeholder|'); sys.exit()

print('ok|' + c['ai']['model'] + '|' + c['feishu']['chat_id'][:12] + '|' + c['ai']['api_key_env'])
PY
)"
  STATUS="${CFG_OUT%%|*}"
  REST="${CFG_OUT#*|}"
  case "$STATUS" in
    ok)
      MODEL="$(echo "$REST" | cut -d'|' -f1)"
      CHAT_PREFIX="$(echo "$REST" | cut -d'|' -f2)"
      KEY_ENV="$(echo "$REST" | cut -d'|' -f3)"
      pass "config.json valid"
      info "Model: $MODEL"
      info "Chat ID: ${CHAT_PREFIX}..."
      info "API key env: \$$KEY_ENV"
      ;;
    missing)       fail "config.json missing fields: $REST" ;;
    bad_identity)  fail "feishu.identity must be 'bot', got: $REST" ;;
    placeholder)   fail "feishu.chat_id is still a placeholder (oc_REPLACE_...)" ;;
    parse_error)   fail "config.json parse error: $REST" ;;
  esac
else
  fail "config.json not found"
fi

# ════════════════════════════════════════════════════════════
header "4. Credentials (read-only — no keys printed)"
# ════════════════════════════════════════════════════════════

# GEMINI_API_KEY visibility
GEMINI_LEN=0
if [ -n "${GEMINI_API_KEY:-}" ]; then
  GEMINI_LEN=${#GEMINI_API_KEY}
fi
if [ $GEMINI_LEN -eq 0 ]; then
  # Check well-known shell configs
  for f in ~/.zshrc ~/.bash_profile ~/.profile; do
    if [ -f "$f" ] && grep -q '^export GEMINI_API_KEY=' "$f" 2>/dev/null; then
      info "GEMINI_API_KEY defined in $f (run.sh --production will load it)"
      GEMINI_LEN=1
      break
    fi
  done
fi
if [ $GEMINI_LEN -gt 0 ]; then
  pass "GEMINI_API_KEY reachable"
else
  fail "GEMINI_API_KEY not in env or ~/.zshrc or ~/.bash_profile"
fi

# lark-cli
if command -v lark-cli >/dev/null 2>&1; then
  LARK_VER="$(lark-cli --version 2>&1 | grep -o 'version [0-9.]*' | head -1)"
  pass "lark-cli installed ($LARK_VER)"

  # Try listing chats — this proves app_id + app_secret are valid
  if lark-cli im chats list --as bot > /tmp/preflight_chats.json 2>/dev/null; then
    CHAT_COUNT="$(python3 -c "import json; print(len(json.load(open('/tmp/preflight_chats.json')).get('data',{}).get('items',[])))" 2>/dev/null || echo 0)"
    if [ "$CHAT_COUNT" -gt 0 ]; then
      pass "lark-cli bot sees $CHAT_COUNT chat(s) — credentials valid"

      # Verify target chat is reachable
      TARGET="$(python3 -c "import json; print(json.load(open('$REPO/config.json'))['feishu']['chat_id'])" 2>/dev/null)"
      if [ -n "$TARGET" ]; then
        FOUND="$(python3 - << PY 2>/dev/null
import json
d = json.load(open('/tmp/preflight_chats.json'))
for c in d.get('data', {}).get('items', []):
    if c.get('chat_id') == '$TARGET':
        print('yes|' + c.get('name', '(no name)')); break
else:
    print('no|')
PY
)"
        if [[ "$FOUND" == yes* ]]; then
          NAME="${FOUND#yes|}"
          pass "Target group reachable: $NAME"
        else
          fail "Bot is NOT in target group ${TARGET:0:12}... — pull bot into the group"
        fi
      fi
    else
      warn "Bot sees 0 chats — may not be in any group"
    fi
    rm -f /tmp/preflight_chats.json
  else
    fail "lark-cli bot list failed — app credentials may be invalid or expired"
  fi
else
  fail "lark-cli not installed (install: npm i -g @larksuite/cli)"
fi

# ════════════════════════════════════════════════════════════
header "5. Upstream feed (raw.githubusercontent.com)"
# ════════════════════════════════════════════════════════════

FEED_URL="$(python3 -c "import json; print(json.load(open('$REPO/config.json'))['feed_url'])" 2>/dev/null || echo "")"
if [[ "$FEED_URL" == http* ]]; then
  HTTP_CODE="$(curl -sS -o /tmp/preflight_feed.json -w "%{http_code}" "$FEED_URL" 2>/dev/null || echo 000)"
  if [ "$HTTP_CODE" = "200" ]; then
    FEED_OUT="$(python3 - << 'PY' 2>/dev/null
import json, datetime as dt, sys
try:
    d = json.load(open('/tmp/preflight_feed.json'))
    total = d.get('stats', {}).get('totalArticles', 0)
    has_copper = 'yes' if d.get('copper') else 'no'
    gen_at = d.get('generatedAt', '')
    age_h = -1
    if gen_at:
        try:
            t = dt.datetime.fromisoformat(gen_at.replace('Z','+00:00'))
            age_h = (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600
        except Exception:
            pass
    print(f'{total}|{has_copper}|{gen_at}|{age_h:.1f}')
except Exception as e:
    print(f'err|{e}')
PY
)"
    if [[ "$FEED_OUT" == err* ]]; then
      fail "Feed JSON parse error: ${FEED_OUT#err|}"
    else
      TOTAL="$(echo "$FEED_OUT" | cut -d'|' -f1)"
      HAS_COPPER="$(echo "$FEED_OUT" | cut -d'|' -f2)"
      GEN_AT="$(echo "$FEED_OUT" | cut -d'|' -f3)"
      AGE_H="$(echo "$FEED_OUT" | cut -d'|' -f4)"
      pass "Feed reachable (HTTP 200): $TOTAL articles, copper=$HAS_COPPER"
      info "Generated: $GEN_AT (${AGE_H}h ago)"

      AGE_INT="${AGE_H%.*}"
      if [ -n "$AGE_INT" ] && [ "$AGE_INT" -gt 30 ] 2>/dev/null; then
        warn "Feed is ${AGE_H}h old (>30h) — upstream CI may have stalled"
      elif [ -n "$AGE_INT" ] && [ "$AGE_INT" -ge 0 ]; then
        pass "Feed freshness OK (${AGE_H}h < 30h)"
      fi

      if [ "$TOTAL" -lt 30 ] 2>/dev/null; then
        warn "Only $TOTAL articles (<30) — digest quality may suffer"
      fi
      if [ "$HAS_COPPER" != "yes" ]; then
        warn "No copper data — digest section 5 will be empty"
      fi
    fi
    rm -f /tmp/preflight_feed.json
  else
    fail "Feed HTTP $HTTP_CODE (expected 200) — network or upstream failure"
  fi
else
  info "feed_url is local path: $FEED_URL (skip HTTP check)"
fi

# ════════════════════════════════════════════════════════════
header "6. OpenClaw cron / launchd schedule"
# ════════════════════════════════════════════════════════════

CRON_FOUND=0

# OpenClaw cron
CRON_FILE=~/.openclaw/cron/jobs.json
if [ -f "$CRON_FILE" ]; then
  pass "OpenClaw cron file: $CRON_FILE"
  JOB_OUT="$(python3 - << 'PY' 2>/dev/null
import json, os
try:
    data = json.load(open(os.path.expanduser('~/.openclaw/cron/jobs.json')))
    jobs = data if isinstance(data, list) else data.get('jobs', [])
    if isinstance(data, dict) and not jobs:
        jobs = list(data.values())
except Exception as e:
    print('err|'+str(e)); raise SystemExit

matching = []
for j in jobs:
    if not isinstance(j, dict): continue
    blob = json.dumps(j, ensure_ascii=False)
    if 'tang-energy-feed' in blob or 'energy-daily-digest' in blob or '零碳能源' in blob or '早报' in blob:
        matching.append(j)

if not matching:
    print(f'none|total_jobs={len(jobs)}')
else:
    j = matching[0]
    enabled = j.get('enabled', None)
    cron = j.get('cron', j.get('schedule', j.get('cron_expression', '?')))
    tz = j.get('tz', j.get('timezone', '?'))
    nxt = j.get('next_run_at', j.get('nextRunAt', j.get('next_run', '?')))
    cmd = str(j.get('command', j.get('cmd', '?')))[:100]
    has_prod = '--production' in cmd
    print(f'found|{enabled}|{cron}|{tz}|{nxt}|{has_prod}|{cmd}')
PY
)"
  case "${JOB_OUT%%|*}" in
    found)
      CRON_FOUND=1
      ENABLED="$(echo "$JOB_OUT" | cut -d'|' -f2)"
      CRON_EXPR="$(echo "$JOB_OUT" | cut -d'|' -f3)"
      JOB_TZ="$(echo "$JOB_OUT" | cut -d'|' -f4)"
      NEXT_RUN="$(echo "$JOB_OUT" | cut -d'|' -f5)"
      HAS_PROD="$(echo "$JOB_OUT" | cut -d'|' -f6)"
      CMD="$(echo "$JOB_OUT" | cut -d'|' -f7-)"

      if [ "$ENABLED" = "True" ] || [ "$ENABLED" = "true" ]; then
        pass "Job enabled"
      else
        fail "Job NOT enabled (enabled=$ENABLED)"
      fi
      info "Schedule: $CRON_EXPR ($JOB_TZ)"
      info "Next run: $NEXT_RUN"
      info "Command: ${CMD:0:80}"
      if [ "$HAS_PROD" = "True" ]; then
        pass "Command includes --production"
      else
        warn "Command missing --production flag (daily run may not archive)"
      fi
      ;;
    none) warn "No tang-energy-feed job in OpenClaw cron (${JOB_OUT#none|})" ;;
    err)  warn "jobs.json unreadable: ${JOB_OUT#err|}" ;;
  esac
else
  info "No OpenClaw cron file (not using OpenClaw?)"
fi

# launchd fallback
if launchctl list 2>/dev/null | grep -q energy-daily-digest; then
  pass "launchd has com.tang.energy-daily-digest"
  CRON_FOUND=1
fi

if [ $CRON_FOUND -eq 0 ]; then
  fail "NO scheduler found (no OpenClaw cron job, no launchd) — 10:30 cron won't fire"
fi

# OpenClaw gateway process
if launchctl list 2>/dev/null | grep -qi openclaw; then
  pass "OpenClaw agent/gateway present in launchctl"
else
  warn "No openclaw service in launchctl — gateway may be down"
fi

# ════════════════════════════════════════════════════════════
header "7. Runtime state (.last-sent-date / archive)"
# ════════════════════════════════════════════════════════════

TODAY="$(date +%Y-%m-%d)"
if [ -f "$REPO/.last-sent-date" ]; then
  LAST_SENT="$(cat $REPO/.last-sent-date | tr -d '[:space:]')"
  if [ "$LAST_SENT" = "$TODAY" ]; then
    warn ".last-sent-date is TODAY ($LAST_SENT) — next production run will be skipped"
    info "If you want to force resend today, delete it: rm $REPO/.last-sent-date"
  else
    pass ".last-sent-date = $LAST_SENT (not today, next cron will fire normally)"
  fi
else
  pass "No .last-sent-date — next production run will execute cleanly"
fi

if [ -d "$REPO/archive" ]; then
  ARCHIVE_COUNT="$(find $REPO/archive -name '*-input.json' 2>/dev/null | wc -l | tr -d ' ')"
  info "Archive contains $ARCHIVE_COUNT past digest(s)"
  if [ -f "$REPO/archive/seen-urls.json" ]; then
    SEEN="$(python3 -c "import json; print(len(json.load(open('$REPO/archive/seen-urls.json')).get('entries',[])))" 2>/dev/null || echo 0)"
    info "7-day dedup cache: $SEEN URL(s)"
  fi
fi

# ════════════════════════════════════════════════════════════
header "8. Sleep prevention (critical for Mac mini)"
# ════════════════════════════════════════════════════════════

if command -v pmset >/dev/null 2>&1; then
  SLEEP_VAL="$(pmset -g 2>/dev/null | grep -E '^[ ]*sleep' | awk '{print $2}' | head -1)"
  info "System sleep setting: ${SLEEP_VAL:-unknown} (0 = never)"

  HAS_WAKE=0
  SCHED="$(pmset -g sched 2>/dev/null || echo "")"
  if echo "$SCHED" | grep -qiE "wakeorpoweron|wake"; then
    HAS_WAKE=1
    WAKE_LINE="$(echo "$SCHED" | grep -iE "wakeorpoweron|wake" | head -1 | sed 's/^ *//')"
    pass "Wake schedule: $WAKE_LINE"
  fi

  if [ "$SLEEP_VAL" = "0" ]; then
    pass "System never sleeps — 10:30 cron always reachable"
  elif [ $HAS_WAKE -eq 1 ]; then
    pass "System sleeps but has wake schedule — cron will fire after wake"
  else
    fail "System sleeps (sleep=$SLEEP_VAL min) AND no wake schedule → HIGH RISK of missing 10:30"
    info "Fix: sudo pmset repeat wakeorpoweron MTWRFSU 10:25:00"
  fi
else
  info "pmset unavailable (not macOS?) — sleep settings not checked"
fi

# ════════════════════════════════════════════════════════════
echo ""
printf "┌──────────────────────────────────────────────────────┐\n"
printf "│  Summary                                              │\n"
printf "└──────────────────────────────────────────────────────┘\n"
printf "  ${GREEN}Passed:   %d${RESET}\n" "$PASSED"
printf "  ${YELLOW}Warnings: %d${RESET}\n" "$WARNS"
printf "  ${RED}Failed:   %d${RESET}\n" "$FAILED"
echo ""

if [ $FAILED -gt 0 ]; then
  printf "${RED}${BOLD}✗ CRITICAL: fix the failed checks before 10:30${RESET}\n\n"
  exit 1
elif [ $WARNS -gt 0 ]; then
  printf "${YELLOW}${BOLD}⚠ Warnings present — review but likely OK${RESET}\n\n"
  exit 2
else
  printf "${GREEN}${BOLD}✓ ALL GREEN — 10:30 cron should fire successfully${RESET}\n\n"
  exit 0
fi
