---
name: energy-daily-digest
description: 零碳能源行业早报 Skill — 每天自动把中国能源/电力/新能源行业新闻和长江铜价推送到飞书群。基于第三代架构：GitHub Actions 自动爬取（上游 crawlers/）→ 公开 JSON feed（feed/feed-digest.json）→ AI 做 remix（scripts/ai_remix.py）→ lark-cli 发送（bot 身份 + interactive 卡片 + 原生 table 组件）。当用户提到"零碳能源早报"、"能源早报"、"电力早报"、"推送今日早报"、"daily energy report"、"生成能源行业早报"、"更新能源 feed"时立即使用此技能。本技能是一个完整的、可 git clone 的、采集+消费一体化的 Skill 包，对齐 follow-builders (zarazhangrui/follow-builders) 的工业级设计——爬取与 remix 完全解耦，AI 只做 remix，不做爬取。任何涉及能源行业日报/早报/资讯推送/数据 feed 的任务，优先使用本技能。
---

# Zero-Carbon Energy Daily Digest

> 一个完整的、采集+消费一体化的能源行业早报系统。
> 灵感：[follow-builders](https://github.com/zarazhangrui/follow-builders) by Zara Zhang Rui

## 这个 Skill 做什么

每天早上自动把最新的中国能源行业新闻 + 长江铜价以**飞书 interactive 卡片**的形式推送到指定的飞书群。

完整流程分为**两层**，**完全解耦**：

```
┌─ 上游（采集层）每天 UTC 22:00 / 北京 06:00 ─────────────┐
│  GitHub Actions 跑 crawlers/                              │
│  ├─ cpnn.com.cn    (电网头条,  ~65 articles/day)          │
│  ├─ nea.gov.cn     (国家能源局, ~48 articles/day)         │
│  └─ cjys.net       (长江铜价)                              │
│  → commit 到 feed/feed-digest.json                        │
└────────────────────────────────────────────────────────────┘
                          ↓
       raw.githubusercontent.com/.../feed-digest.json
        （零 API、零认证、CDN 加速、全球可用）
                          ↓
┌─ 下游（消费层）每天 10:30 本地 launchd 触发 ─────────────┐
│  scripts/run.sh 一键跑完 6 步：                             │
│    1. Load Config         读 config.json                   │
│    2. Fetch Feed          拉 JSON                          │
│    3. Check Content       ≥10 articles 才继续              │
│    4. Classify            按关键词分到 4 候选池             │
│    5. AI Remix            LLM 挑选 + 改写 + 写判断          │
│    6. Build + Deliver     构造飞书卡片 → lark-cli 发送      │
└────────────────────────────────────────────────────────────┘
```

## 六条硬规则（不可协商）

### 1. No web fetching
AI **绝对不上网爬取**。所有原始数据只能来自 `feed-digest.json`。爬取是"脏活"，外包给 GitHub Actions；AI 是"艺术家"，专心做 remix。

### 2. URLs required
每条新闻的 `url` 字段必须是 http/https 开头的完整 URL。禁止编造、禁止缩短、禁止留空。

### 3. No fabrication
AI 只能从 `candidates.json` 提供的候选里挑选和改写。**严禁**凭空编造新闻。

### 4. Bot identity only
发送必须 `lark-cli im +messages-send --as bot`。**禁止** `--as user`（早报是自动化性质，user 身份会造成混淆）。

### 5. Interactive card + native table
消息类型必须 `--msg-type interactive`。铜价必须用飞书卡片 schema 2.0 的原生 `table` 组件。**禁止**用 markdown 表格或 `code_block` 代替（飞书不渲染 markdown 表格，`code_block` 视觉上是代码不是表格）。

### 6. Fixed 6 sections
板块结构固定，标题一字不改：
```
一、今日最重要（3条）
二、政策与行业（3条）
三、湖北本地（2条）      ← 即便没有湖北新闻也不能改标题
四、AI + 电力（2条）
五、铜价与材料（1条）    ← 必须是 table 组件
六、重点机会提示
```

## Delivery Workflow（每次发送跑 6 步）

对齐 follow-builders 的 Content Delivery Workflow：

### Step 1 — Load Config
读取 `config.json` 的 `feed_url`、`feishu.chat_id`、`ai.*`。校验字段完整且不含占位符。

### Step 2 — Fetch Feed
```bash
python3 scripts/fetch_feed.py config.json > /tmp/feed.json
```
从 `feed_url` 下载 `feed-digest.json`。支持 `https://` URL 或本地路径（离线测试用）。

### Step 3 — Check Content
如果 `stats.totalArticles < 10` 或 `copper == null`，**中止流程**并报警。不要发送低质量早报。

### Step 4 — Classify Candidates
```bash
python3 scripts/classify_candidates.py /tmp/feed.json > /tmp/candidates.json
```
按关键词把 100+ 篇新闻预分到 4 个候选池（top3 / policy / hubei / ai_power），每池 5-10 条。**确定性逻辑**，不涉及 AI。

### Step 5 — AI Remix
```bash
python3 scripts/ai_remix.py config.json /tmp/candidates.json > /tmp/input.json
```
调用 OpenAI-compatible LLM。AI 的职责：
- 从每个候选池挑出指定数量（3+3+2+2=10 条）
- 每条改写成 ≤15 字标题 + ≤30 字摘要 + ≤30 字影响分析
- 写铜价判断句（根据涨跌方向）
- 写 4 条"本周关注"

完整 prompt 在 `prompts/remix-instructions.md`。

### Step 6 — Build Card + Deliver
```bash
python3 scripts/build_card.py /tmp/input.json > /tmp/card.json
lark-cli im +messages-send \
  --chat-id "$(jq -r .feishu.chat_id config.json)" \
  --as bot --msg-type interactive \
  --content "$(cat /tmp/card.json)"
```

**完整 6 步封装在 `scripts/run.sh`，一条命令跑完**：
```bash
./scripts/run.sh
```

## Onboarding Flow（第一次使用，9 步）

对齐 follow-builders 的 Onboarding。运行 `./scripts/setup.sh` 后，向导依次处理：

1. **依赖检查** — Python 3.9+、lark-cli、必要时引导安装
2. **时区确认** — 默认北京时间
3. **投递方式** — 目前只支持飞书群（未来可扩展）
4. **飞书 chat_id** — 引导查询并输入 `oc_xxx` 格式
5. **AI Backend 选择** — Gemini 3 Flash（默认）/ Gemini 2.5 Flash / OpenRouter / DeepSeek / OpenAI / 自定义
6. **生成 config.json** — 写入所有配置（**API key 仍然走环境变量，不落盘**）
7. **数据源概览** — 展示上游 feed 当前覆盖哪些源
8. **定时任务** — 可选，安装 `launchd/` 下的 plist 实现每天 10:30 自动推送
9. **欢迎发送** — 立即跑一次完整流程，发一条测试早报到群

完成后用户可随时 `./scripts/run.sh` 手动发，或等 launchd 每天 10:30 自动发。

## AI Backend — OpenAI-compatible 接所有

`scripts/ai_remix.py` 是一个**通用 OpenAI-compatible client**。通过 `config.json` 的 `ai` 块配置，**无需改代码**：

```json
{
  "ai": {
    "provider": "gemini",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "model": "gemini-3-flash",
    "api_key_env": "GEMINI_API_KEY",
    "temperature": 0.3
  }
}
```

支持（但不限于）：

| Provider | base_url | 典型 model | 成本 |
|---|---|---|---|
| **Gemini**（默认）| `.../v1beta/openai` | `gemini-3-flash` | 免费/极低 |
| OpenRouter | `https://openrouter.ai/api/v1` | `google/gemini-2.5-flash` | 按量 |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | 极低 |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | 低 |
| Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | 低 |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | 低 |

**API key 永远通过环境变量传入**（名字由 `api_key_env` 指定），**不写在 config.json 里**。这是硬安全约束——任何文件里都不应出现 key 本身。

## 目录结构

```
tang-energy-feed/                         ← 根目录
├── SKILL.md                              ← 你正在读的这个（灵魂文件）
├── README.md                             ← 项目介绍 + 订阅 URL
├── INSTALL.md                            ← 详细安装指南
├── LICENSE                               ← MIT
├── config.example.json                   ← 配置模板（复制为 config.json）
├── .gitignore                            ← 注意：排除 config.json（含 chat_id）
│
├── .github/workflows/
│   └── daily-crawl.yml                   ← GitHub Actions 定时爬取
│
├── crawlers/                             ← 上游：采集层（CI 运行）
│   ├── requirements.txt
│   ├── common.py                         ← 共享 HTTP/解析工具
│   ├── cpnn.py                           ← 电网头条
│   ├── nea.py                            ← 国家能源局
│   ├── copper.py                         ← 长江铜价
│   ├── bjx.py                            ← 北极星（WAF placeholder）
│   └── aggregate.py                      ← 聚合到 feed-digest.json
│
├── scripts/                              ← 下游：消费层（本地运行）
│   ├── fetch_feed.py                     ← 拉 feed JSON
│   ├── classify_candidates.py            ← 关键词预分类
│   ├── ai_remix.py                       ← LLM remix（默认 Gemini）
│   ├── build_card.py                     ← 构造飞书卡片 JSON
│   ├── run.sh                            ← 一键跑完 6 步
│   └── setup.sh                          ← 9 步交互式安装
│
├── prompts/
│   └── remix-instructions.md             ← ai_remix.py 用的 LLM prompt
│
├── references/                           ← 详细文档
│   ├── data-contract.md                  ← feed-digest.json schema 契约
│   ├── selection-rules.md                ← AI 挑选规则详解
│   ├── lark-setup-guide.md               ← 飞书机器人配置指南
│   └── troubleshooting.md                ← 故障排查
│
├── examples/
│   ├── candidates.sample.json            ← 分类后的候选池示例
│   ├── input.sample.json                 ← AI remix 输出示例
│   └── card.sample.json                  ← 最终飞书卡片示例
│
├── launchd/
│   └── com.tang.energy-daily-digest.plist.template  ← macOS 定时模板
│
└── feed/                                 ← CI 产出（自动 commit）
    ├── .gitkeep
    ├── feed-cpnn.json
    ├── feed-nea.json
    ├── feed-copper.json
    ├── feed-bjx.json
    └── feed-digest.json                  ← ⭐ 消费方拉这个
```

## 分发给新用户

完整安装只需要 **3 行命令**：

```bash
git clone https://github.com/tang730125633/tang-energy-feed.git
cd tang-energy-feed
./scripts/setup.sh
```

`setup.sh` 会走完 9 步 onboarding，完成后系统立即可用。想每天 10:30 自动推送？setup.sh 的 Step 8 会问你是否启用 launchd，选 yes 即可。

## 数据契约

上游 `feed-digest.json` 的 schema 定义在 `references/data-contract.md`。关键字段保证：

- `generatedAt` (ISO 8601)
- `articles[]`，每条 `{id, title, url, publishedAt, source}`
- `copper`，包含 `{mean_price, change, price_range, brand, date}`
- `stats.totalArticles`
- `errors[]`

**非破坏性变更**（加新字段）不需要升级。**破坏性变更**会开新版本 URL（例如 `feed-digest-v2.json`），老版本继续可用。

## 与 follow-builders 的对齐点

| 设计要点 | follow-builders | tang-energy-feed |
|---|---|---|
| 一体化 repo | ✅ | ✅ |
| SKILL.md 在 root | ✅ | ✅ |
| AI 只做 remix | ✅ | ✅ |
| 采集在 GitHub Actions | ✅ | ✅ |
| Feed 作为 git-versioned JSON | ✅ | ✅ |
| 独立 `prompts/` 目录 | ✅ | ✅ |
| 9 步 Onboarding | ✅ | ✅ |
| 6 步 Delivery Workflow | ✅ | ✅ |
| 硬规则明示 | 6 条 | 6 条 |
| Delivery 可 cron 触发 | ✅ | ✅（`launchd/`） |
| 多 backend AI 支持 | 单一 | ✅（任何 OpenAI-compatible） |
| 多语言 README | en + zh-CN | zh-CN（en TODO） |

## 安全约束（重要）

- **永远不要**把 API key 粘贴到 config.json / 聊天 / 截图 / git / 云笔记。key 只在**生成的那一刻** `export` 一次，之后一切都用 `$ENV_VAR` 引用
- **永远不要**用 `--as user` 发早报，自动化推送必须 `--as bot`
- **永远不要**手写飞书卡片 JSON，一律用 `build_card.py` 生成
- 单独发了 `config.json` 给别人？**你的 chat_id 泄漏了**，对方可以冒用（虽然还需要 bot 权限）

## 维护与扩展

- 加新数据源 → 在 `crawlers/` 下加一个 `xxx.py`，在 `daily-crawl.yml` 里加一行 workflow step
- 改 remix 规则 → 编辑 `prompts/remix-instructions.md`
- 换 AI model → 改 `config.json` 的 `ai.model`，不用改代码
- 改定时时间 → 改 `launchd/com.tang.energy-daily-digest.plist.template` 的 `StartCalendarInterval`

**维护者**：Tang (tang730125633@github)
**创建**：2026-04-11
**灵感来源**：Zara Zhang Rui 的 follow-builders
**许可**：MIT
