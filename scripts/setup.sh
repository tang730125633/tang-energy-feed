#!/bin/bash
#
# setup.sh — 9-step interactive onboarding wizard.
# Inspired by follow-builders (zarazhangrui/follow-builders) Onboarding Flow.
#
# Steps:
#   1. Dependency check (Python, lark-cli)
#   2. Timezone confirmation
#   3. Delivery method (currently Feishu only)
#   4. Feishu chat_id capture
#   5. AI backend selection
#   6. Config file generation
#   7. Data source overview
#   8. launchd scheduling (macOS only)
#   9. First test run + welcome digest

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Color helpers
cyan()   { printf '\033[36m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*"; }
dim()    { printf '\033[2m%s\033[0m\n' "$*"; }

ask() {
  local prompt="$1"
  local default="${2:-}"
  local answer
  if [ -n "$default" ]; then
    read -r -p "$prompt [$default]: " answer
    echo "${answer:-$default}"
  else
    read -r -p "$prompt: " answer
    echo "$answer"
  fi
}

cat << 'BANNER'

╔══════════════════════════════════════════════════════════════╗
║  零碳能源行业早报 Skill — 安装向导 v1.0                        ║
║  energy-daily-digest setup wizard                             ║
║                                                               ║
║  这是一个基于 tang-energy-feed 订阅的飞书能源早报系统。         ║
║  安装完成后，每天早上会自动把最新能源行业新闻 + 铜价推送到群。    ║
║                                                               ║
║  架构：GitHub Actions 爬取（上游）→ 你的 AI 做 remix → 飞书    ║
║  设计哲学：AI 只做 remix，不做爬取（对齐 follow-builders）      ║
╚══════════════════════════════════════════════════════════════╝

BANNER

# =============================================================================
# Step 1/9: Dependency check
# =============================================================================
cyan "▸ Step 1/9: 依赖检查"

missing=0
check_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    green "  ✓ $1"
  else
    red "  ✗ $1 未安装"
    return 1
  fi
}

check_cmd python3 || missing=1

if ! check_cmd lark-cli; then
  yellow "  lark-cli 未安装。是否现在安装? (需要 Node.js + npm)"
  ans=$(ask "安装 lark-cli? (y/n)" "y")
  if [ "$ans" = "y" ]; then
    if command -v npm >/dev/null 2>&1; then
      npm install -g @larksuite/cli || { red "lark-cli 安装失败"; missing=1; }
    else
      red "  npm 未安装。请先安装 Node.js: https://nodejs.org/"
      missing=1
    fi
  else
    missing=1
  fi
fi

if [ $missing -eq 1 ]; then
  red ""
  red "依赖缺失，请先安装后重新运行 setup.sh"
  exit 1
fi

# =============================================================================
# Step 2/9: Timezone
# =============================================================================
echo ""
cyan "▸ Step 2/9: 时区确认"
echo "  当前系统时区: $(date +%Z) ($(date +%z))"
echo "  早报将默认在北京时间 10:30 自动推送（如启用定时）"

# =============================================================================
# Step 3/9: Delivery method
# =============================================================================
echo ""
cyan "▸ Step 3/9: 投递方式"
echo "  目前仅支持飞书群聊。未来版本可能支持邮件 / Telegram。"
DELIVERY="feishu"

# =============================================================================
# Step 4/9: Feishu chat_id
# =============================================================================
echo ""
cyan "▸ Step 4/9: 飞书 chat_id"
echo ""
echo "  前置要求："
echo "    1. 已在飞书开发者后台创建自建应用"
echo "    2. 开通 im:message:send_as_bot + im:chat:read 权限"
echo "    3. 将机器人拉进目标群"
echo "    4. 已运行过 lark-cli config init 并配好 App ID / Secret"
echo ""
echo "  详细步骤见 references/lark-setup-guide.md"
echo ""
dim "  查询你的群列表:  lark-cli im chats list --as bot"
echo ""

CHAT_ID=$(ask "输入目标群的 chat_id (oc_xxxxxxxxxxxx)")
if [[ ! "$CHAT_ID" =~ ^oc_ ]]; then
  red "格式错误: chat_id 必须以 oc_ 开头"
  exit 1
fi
green "  ✓ chat_id OK: ${CHAT_ID:0:12}..."

# =============================================================================
# Step 5/9: AI Backend selection
# =============================================================================
echo ""
cyan "▸ Step 5/9: 选择 AI Backend"
echo ""
echo "  早报的内容 remix 需要调用一个 LLM（每天仅 1 次，消耗极少）。"
echo "  本系统支持任何 OpenAI-compatible 的 API:"
echo ""
echo "    1) Gemini 3 Flash      ⭐ 推荐（快 + 额度充裕 + 质量足够）"
echo "    2) Gemini 2.5 Flash    (备选，免费额度丰富)"
echo "    3) OpenRouter          (支持所有模型，需要充值)"
echo "    4) DeepSeek            (国内直连，超便宜)"
echo "    5) OpenAI              (稳定，稍贵)"
echo "    6) 自定义              (任何 OpenAI-compatible 端点)"
echo ""
choice=$(ask "选择 (1-6)" "1")

case "$choice" in
  1)
    AI_PROVIDER="gemini"
    AI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
    AI_MODEL="gemini-3-flash"
    AI_KEY_ENV="GEMINI_API_KEY"
    AI_KEY_URL="https://aistudio.google.com/apikey"
    ;;
  2)
    AI_PROVIDER="gemini"
    AI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
    AI_MODEL="gemini-2.5-flash"
    AI_KEY_ENV="GEMINI_API_KEY"
    AI_KEY_URL="https://aistudio.google.com/apikey"
    ;;
  3)
    AI_PROVIDER="openrouter"
    AI_BASE_URL="https://openrouter.ai/api/v1"
    AI_MODEL=$(ask "模型名" "google/gemini-2.5-flash")
    AI_KEY_ENV="OPENROUTER_API_KEY"
    AI_KEY_URL="https://openrouter.ai/keys"
    ;;
  4)
    AI_PROVIDER="deepseek"
    AI_BASE_URL="https://api.deepseek.com/v1"
    AI_MODEL="deepseek-chat"
    AI_KEY_ENV="DEEPSEEK_API_KEY"
    AI_KEY_URL="https://platform.deepseek.com/api_keys"
    ;;
  5)
    AI_PROVIDER="openai"
    AI_BASE_URL="https://api.openai.com/v1"
    AI_MODEL=$(ask "模型名" "gpt-4o-mini")
    AI_KEY_ENV="OPENAI_API_KEY"
    AI_KEY_URL="https://platform.openai.com/api-keys"
    ;;
  6)
    AI_PROVIDER="custom"
    AI_BASE_URL=$(ask "OpenAI-compatible base URL")
    AI_MODEL=$(ask "模型名")
    AI_KEY_ENV=$(ask "API key 环境变量名" "OPENAI_API_KEY")
    AI_KEY_URL=""
    ;;
  *)
    red "无效选择"
    exit 1
    ;;
esac

echo ""
green "  ✓ 已选: $AI_PROVIDER / $AI_MODEL"
echo ""
if [ -n "$AI_KEY_URL" ]; then
  yellow "  获取 API key: $AI_KEY_URL"
fi
echo ""
echo "  ⚠️ 重要: 不要把 API key 粘贴到这里或任何文件里。"
echo "     正确做法是设为环境变量:"
echo ""
echo "     export $AI_KEY_ENV=\"你的key\""
echo "     echo 'export $AI_KEY_ENV=\"你的key\"' >> ~/.zshrc"
echo ""

# Check if key is already set
if [ -n "${!AI_KEY_ENV:-}" ]; then
  green "  ✓ 检测到 \$$AI_KEY_ENV 已设置（长度 ${#AI_KEY_ENV} 字符）"
else
  yellow "  ⚠ 未检测到 \$$AI_KEY_ENV。请设置后再运行 ./scripts/run.sh"
fi

# =============================================================================
# Step 6/9: Generate config.json
# =============================================================================
echo ""
cyan "▸ Step 6/9: 生成 config.json"

cat > "$REPO_ROOT/config.json" << CONFIG
{
  "feed_url": "https://raw.githubusercontent.com/tang730125633/tang-energy-feed/main/feed/feed-digest.json",
  "feishu": {
    "chat_id": "$CHAT_ID",
    "identity": "bot"
  },
  "ai": {
    "provider": "$AI_PROVIDER",
    "base_url": "$AI_BASE_URL",
    "model": "$AI_MODEL",
    "api_key_env": "$AI_KEY_ENV",
    "temperature": 0.3,
    "response_format_json": true
  },
  "lookback_hours": 48
}
CONFIG

green "  ✓ config.json 已生成"

# =============================================================================
# Step 7/9: Data source overview
# =============================================================================
echo ""
cyan "▸ Step 7/9: 数据源概览"
echo ""
echo "  上游 feed (tang-energy-feed) 当前覆盖:"
echo "    ✓ 电网头条         (cpnn.com.cn)     ~65 articles/day"
echo "    ✓ 国家能源局       (nea.gov.cn)      ~48 articles/day"
echo "    ✓ 长江现货铜价     (cjys.net)        1 price/day"
echo "    ⚠ 北极星电力网     (bjx.com.cn)      被 Aliyun WAF 挡住"
echo ""
echo "  需要加新源? 到 https://github.com/tang730125633/tang-energy-feed 提 PR"

# =============================================================================
# Step 8/9: launchd scheduling (macOS only)
# =============================================================================
echo ""
cyan "▸ Step 8/9: 定时任务（可选）"

if [ "$(uname)" = "Darwin" ]; then
  echo ""
  echo "  检测到 macOS。是否启用 launchd 定时任务（每天 10:30 自动推送）?"
  schedule=$(ask "启用定时? (y/n)" "n")

  if [ "$schedule" = "y" ]; then
    PLIST_SRC="$REPO_ROOT/launchd/com.tang.energy-daily-digest.plist.template"
    PLIST_DST="$HOME/Library/LaunchAgents/com.tang.energy-daily-digest.plist"

    if [ ! -f "$PLIST_SRC" ]; then
      red "  ✗ 找不到模板: $PLIST_SRC"
    else
      mkdir -p "$HOME/Library/LaunchAgents"
      sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$PLIST_SRC" > "$PLIST_DST"
      launchctl unload "$PLIST_DST" 2>/dev/null || true
      launchctl load "$PLIST_DST"
      green "  ✓ launchd 已加载"
      echo "  日志: tail -f /tmp/energy-daily-digest.log"
      echo "  卸载: launchctl unload $PLIST_DST && rm $PLIST_DST"
    fi
  fi
else
  echo ""
  echo "  非 macOS。请使用 crontab 配置定时任务:"
  echo "    crontab -e"
  echo "    # 加入下面这一行（每天 10:30 触发）"
  echo "    30 10 * * *  $REPO_ROOT/scripts/run.sh >> /tmp/energy-daily-digest.log 2>&1"
fi

# =============================================================================
# Step 9/9: Test run
# =============================================================================
echo ""
cyan "▸ Step 9/9: 测试发送"
echo ""
echo "  现在立即跑一次完整流程（fetch → classify → AI remix → 发送）?"
echo "  测试会发一条真实的早报到你的群里。"
test=$(ask "测试? (y/n)" "y")

if [ "$test" = "y" ]; then
  echo ""
  echo "  开始测试..."
  echo ""
  bash "$REPO_ROOT/scripts/run.sh" && {
    echo ""
    green "╔══════════════════════════════════════════════════════╗"
    green "║  ✅ 安装完成！测试早报已发送到群                       ║"
    green "╚══════════════════════════════════════════════════════╝"
  } || {
    echo ""
    red "╔══════════════════════════════════════════════════════╗"
    red "║  ⚠ 测试失败                                          ║"
    red "╚══════════════════════════════════════════════════════╝"
    yellow "排障: cat references/troubleshooting.md"
    exit 1
  }
fi

echo ""
cat << 'DONE'
常用命令:
  手动发送:      ./scripts/run.sh
  查日志:        tail -f /tmp/energy-daily-digest.log
  改配置:        编辑 config.json
  排障:          cat references/troubleshooting.md
  更新上游数据:  不用管，GitHub Actions 每天 06:00 自动更新

如果遇到问题，随时查 references/troubleshooting.md。

晚安 🌙
DONE
