# tang-energy-feed

> 零碳能源行业早报的**完整可分发 Skill 包**——采集 + 消费 + 定时一体化。
> 架构灵感来自 [follow-builders](https://github.com/zarazhangrui/follow-builders) 的第三代设计。

---

## 🎯 这是什么

一个每天自动生成并推送到飞书群的**零碳能源行业早报系统**，包括：

- 🌍 **今日最重要**（3条）— 国家级数据、重大项目、高层政策
- 📋 **政策与行业**（3条）— 新规、市场机制、产业链突破
- 🏞️ **湖北本地**（2条）— 湖北 + 周边省份动态
- 🤖 **AI + 电力**（2条）— 算电协同、虚拟电厂、数据中心绿电
- 💰 **长江1#铜价**（原生表格）— 均价/涨跌/区间/牌号/日期
- 🎯 **本周关注**（4条）— 投资机会与市场展望

所有新闻标题都是**可点击超链接**，铜价是**真正的飞书原生表格**，整张卡片由飞书原生渲染。

---

## 📦 架构（第三代：采集与 AI 解耦）

```
┌──────────────────────────────────────────────────────────┐
│  Upstream (CI)  — GitHub Actions 每天 06:00 BJT          │
│  crawlers/*.py → feed/feed-digest.json → git commit      │
└─────────────────────┬────────────────────────────────────┘
                      │
                      │ raw.githubusercontent.com
                      │ (零 API、零认证、CDN 加速)
                      ↓
┌──────────────────────────────────────────────────────────┐
│  Downstream (Local) — 用户本地 launchd 每天 10:30         │
│  scripts/run.sh:                                          │
│    fetch → classify → AI remix → build → lark-cli send    │
└──────────────────────────────────────────────────────────┘
```

**核心原则**：**AI 只做 remix，不做爬取**。爬取是工程问题（反爬、认证、超时），交给 CI；remix 是创作问题（判断、改写、分析），交给 AI。

---

## 🚀 快速开始（3 行）

```bash
git clone https://github.com/tang730125633/tang-energy-feed.git
cd tang-energy-feed
./scripts/setup.sh
```

`setup.sh` 是一个 9 步交互式向导（对齐 follow-builders 的 Onboarding Flow）：

1. 依赖检查（Python + lark-cli）
2. 时区确认
3. 投递方式
4. 飞书 chat_id 输入
5. AI backend 选择（推荐 Gemini 3 Flash，**免费**）
6. 生成 `config.json`
7. 数据源概览
8. 定时任务（可选 launchd）
9. 测试发送

**15-20 分钟完成全部配置**，从此每天 10:30 自动发送。

---

## 🔗 订阅 URL（消费端用这个）

**聚合 feed（推荐）**：
```
https://raw.githubusercontent.com/tang730125633/tang-energy-feed/main/feed/feed-digest.json
```

**单源 feed**（按需）：
```
.../feed/feed-cpnn.json    电网头条
.../feed/feed-nea.json     国家能源局
.../feed/feed-copper.json  长江铜价
.../feed/feed-bjx.json     北极星电力网（目前 WAF 受阻）
```

**零 API、零认证、全球 CDN**。任何 AI / 脚本 / 程序都可以直接拉。

---

## 📊 数据源状态

| 源 | URL | 状态 | 说明 |
|---|---|---|---|
| 电网头条 | cpnn.com.cn | ✅ 主力 | 国家电网官媒，~65 articles/day |
| 国家能源局 | nea.gov.cn | ✅ 政策 | 官方源，~48 articles/day |
| 长江铜价 | cjys.net | ✅ 稳定 | 明文 HTML 表格 |
| 北极星电力网 | bjx.com.cn | ⚠️ 受阻 | Aliyun WAF，Day 2+ 用 playwright 解决 |

---

## 🧠 AI Backend — 自由切换

`scripts/ai_remix.py` 是一个**通用 OpenAI-compatible client**。通过 `config.json` 一行配置切换 backend：

```json
"ai": {
  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
  "model": "gemini-3-flash",
  "api_key_env": "GEMINI_API_KEY"
}
```

支持 Gemini / OpenRouter / DeepSeek / OpenAI / Kimi / 通义千问 / 任何 OpenAI-compatible 端点。**代码无需任何修改**。

**API key 永远通过环境变量传入**（`export GEMINI_API_KEY=xxx`），不写在 config.json 里——这是硬安全约束。

---

## 📁 目录结构

```
tang-energy-feed/
├── SKILL.md                    # 灵魂文件，任何 AI 读这个就能用
├── README.md                   # 你正在读的这个
├── INSTALL.md                  # 详细安装指南
├── config.example.json         # 配置模板
│
├── .github/workflows/          # 上游 GitHub Actions
├── crawlers/                   # 上游：Python 爬虫
├── scripts/                    # 下游：用户本地脚本
│   ├── fetch_feed.py
│   ├── classify_candidates.py
│   ├── ai_remix.py             # ⭐ 通用 OpenAI-compatible client
│   ├── build_card.py
│   ├── run.sh                  # ⭐ 一键跑 6 步 delivery workflow
│   └── setup.sh                # ⭐ 9 步 onboarding 向导
├── prompts/
│   └── remix-instructions.md   # 给 AI 的 remix 指令
├── references/                 # 详细文档
├── examples/                   # 示例 JSON
├── launchd/                    # macOS 定时任务模板
└── feed/                       # ⭐ CI 产出（自动 commit）
    └── feed-digest.json        # ⭐ 订阅方拉这个
```

---

## 🔐 三条硬安全规则

1. **身份必须 `--as bot`**（自动化推送不能冒用真人身份）
2. **格式必须 `interactive` 卡片 + 原生 `table` 组件**（飞书不渲染 markdown 表格）
3. **板块固定 6 个**，标题一字不改（即便没有湖北新闻也要保留"三、湖北本地"标题，用周边省份填充）

完整的硬规则见 `SKILL.md`。

---

## 🏗️ 想对外分发 / 给同事用？

这个 repo 就是一个**完整的 Skill 包**。分发给别人只需要告诉他们：

```
git clone https://github.com/tang730125633/tang-energy-feed.git
cd tang-energy-feed && ./scripts/setup.sh
```

对方按 9 步向导填完之后，他的 AI 就能用你维护的同一份 feed 每天生成自己的早报。**一份 feed，N 个订阅者**。

---

## 🛣️ Roadmap

- [x] **Day 1**：cpnn + nea + copper 三源直爬跑通；本地端到端测试通过
- [x] **Day 1**：消费端 Skill 包（scripts + prompts + setup.sh）对齐 follow-builders
- [ ] **Day 2**：修 bjx WAF（playwright 独立 workflow）
- [ ] **Day 3**：加定时任务 + 给首个订阅者交付
- [ ] **Week 2**：补 ne21.com、iesplaza.com 两个垂直源
- [ ] **Week 3**：详情页抓取，给 feed 加 `summary` 字段
- [ ] **Month 2**：中部能源专题 feed（湖北/湖南/河南/江西/安徽）
- [ ] **Month 3**：英文 README + 国际推广

---

## 📚 文档导航

- **我要用它** → 读 `INSTALL.md`
- **我想理解架构** → 读 `SKILL.md`（灵魂文件）
- **我想看数据格式** → 读 `references/data-contract.md`
- **我想调 AI remix 规则** → 读 `references/selection-rules.md` + `prompts/remix-instructions.md`
- **遇到问题了** → 读 `references/troubleshooting.md`
- **要配飞书机器人** → 读 `references/lark-setup-guide.md`

---

## 🙏 致谢

- [Zara Zhang Rui](https://github.com/zarazhangrui) 的 **follow-builders** 项目——第三代架构的启蒙
- [Anthropic](https://www.anthropic.com) 的 Claude Code——帮我在一个晚上从零搭起整套系统
- 所有愿意把采集脏活放到 CI、让 AI 专心做创作的工程师

---

## 📄 License

MIT © 2026 Tang ([tang730125633](https://github.com/tang730125633))

**欢迎 Fork / PR / 提 issue**。想要新的数据源？开个 issue 我加。想做其他行业的 feed？Fork 这个 repo 改 crawlers 就行。
