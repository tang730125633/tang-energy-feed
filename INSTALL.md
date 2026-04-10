# 安装指南

这份文档面向**消费端部署者**（Tang 自己或任何订阅者，比如戴总）。整个过程约 **15-20 分钟**。

## 🎯 重要的认知前提

在开始之前，请理解一件事——**这个 repo 是 public 的**，任何人 `git clone` 都不需要登录任何 GitHub 账号。消费端从头到尾**不和 GitHub 账号产生任何交互**，它只是一个"公开 URL 的下载者"。

这意味着：
- ❌ **不需要** 登录 Tang 的 GitHub 账号
- ❌ **不需要** SSH key、不需要 Personal Access Token
- ❌ **不需要** 任何 GitHub 凭据
- ✅ 只需要 `git clone` 一次（公开下载）
- ✅ 之后每天跑 `scripts/run.sh` 访问公开的 `raw.githubusercontent.com` URL

部署者**自己**需要准备的凭据（和 Tang 的 GitHub 完全无关）：

| 凭据 | 从哪获取 | 存在哪里 |
|---|---|---|
| Gemini API key | https://aistudio.google.com/apikey（免费） | 你自己电脑的 `~/.zshrc` 环境变量 |
| 飞书 App ID + Secret | https://open.feishu.cn/app 创建自建应用 | 你自己电脑的 `lark-cli` 配置 |
| 飞书群 chat_id | 用 `lark-cli im chats list --as bot` 查 | 你自己电脑的 `config.json` |

---

## 🅰️ 路径 A — 本地 launchd（推荐，适合有 7×24 电脑的部署者）

这是 **戴总 Mac mini 的推荐方案**，因为：
- 那台 Mac mini 本来就是 OpenClaw 定时任务用的，7×24 开机
- 本地跑不依赖外网（爬取部分的外网由 GitHub Actions 代劳）
- 消费端数据流完全在 Mac mini 内：`curl → Python → lark-cli → 飞书群`

### 需要准备

- macOS（路径 A 的 launchd 是 macOS 专有；Linux 用 crontab，看 Step 8）
- Python 3.9+
- Node.js 18+（用于 `lark-cli`；如果不想装，可以用纯 Python 的 `send_lark.py`）
- 一个飞书企业账号
- 能在飞书开发者后台创建自建应用的权限
- 一个 Gemini API key（免费）

### Step 1：克隆 repo（公开下载，无需登录）

```bash
cd ~/code   # 或者任何不在 iCloud / OneDrive 同步目录下的位置
git clone https://github.com/tang730125633/tang-energy-feed.git
cd tang-energy-feed
```

**注意**：不要把 repo 放在 iCloud / Dropbox / OneDrive 同步目录里，会和 git 冲突。

### Step 2：申请 Gemini API key 并 export

```bash
# 1. 去 https://aistudio.google.com/apikey 点 "Create API key"
# 2. 复制生成的 key（不要粘贴到任何地方！）
# 3. 在终端设置环境变量：
export GEMINI_API_KEY="你刚复制的key"
echo 'export GEMINI_API_KEY="你刚复制的key"' >> ~/.zshrc

# 4. 验证（只打印长度和前缀，不打印完整 key）
echo "GEMINI_API_KEY length: ${#GEMINI_API_KEY}"
```

**安全警告**：永远只在 `export` 那一次粘贴真实的 key。之后的所有验证命令只用 `$GEMINI_API_KEY` 这个"标签"引用，不要再把真实 key 写进任何命令或文件。

### Step 3：配置飞书自建应用 + bot

**详细步骤**见 `references/lark-setup-guide.md`，**核心要点**：

1. 到 https://open.feishu.cn/app 点 "创建企业自建应用"
2. 开通 scope：`im:message:send_as_bot` 和 `im:chat:read`
3. 发布应用的一个版本
4. **把机器人手动拉进目标群**（群设置 → 群机器人 → 添加）
5. 安装并配置 `lark-cli`：
   ```bash
   npm install -g @larksuite/cli
   lark-cli config init
   # 按提示填 App ID 和 App Secret
   ```
6. 查询目标群的 chat_id：
   ```bash
   lark-cli im chats list --as bot
   # 复制 oc_xxx 开头的 chat_id
   ```

### Step 4：运行 setup.sh 向导

```bash
cd ~/code/tang-energy-feed
./scripts/setup.sh
```

这是一个 9 步交互式向导：

1. 依赖检查
2. 时区确认
3. 投递方式（飞书）
4. 输入刚才拿到的 chat_id
5. 选 AI backend（默认 Gemini 3 Flash，免费）
6. 生成 `config.json`
7. 显示数据源状态
8. **启用 launchd 定时任务**（回答 `y`）
9. 立即测试发送一条

### Step 5：验证 launchd 已启用

```bash
launchctl list | grep energy-daily-digest
# 应该看到一行 com.tang.energy-daily-digest 的记录

# 查看日志位置
tail -f /tmp/energy-daily-digest.log
```

完成。从此每天 10:30 自动推送到飞书群，Mac mini 不关机就不会停。

### 手动触发（随时可用）

```bash
cd ~/code/tang-energy-feed
./scripts/run.sh
```

---

## 🅱️ 路径 B — 纯 GitHub Actions 云端运行（备选）

适合"没有 7×24 电脑"的部署者。戴总已有 Mac mini 跑 OpenClaw 所以**不需要这条路径**，但保留作为 Mac mini 维护期的备份方案。

### 需要准备

- 一个 GitHub 账号（你自己的，不是 Tang 的！）
- 一个 Gemini API key
- 一个飞书自建应用（同 Path A 的 Step 3）
- 飞书群 chat_id

### Step 1：Fork 这个 repo 到你自己的账号

打开 https://github.com/tang730125633/tang-energy-feed 点右上角 **Fork**。

你的 fork 会变成 `https://github.com/<你的用户名>/tang-energy-feed`。

### Step 2：在你的 fork 里配置 4 个 secrets

进入你的 fork → Settings → Secrets and variables → Actions → New repository secret

添加这 4 个：

| Secret 名 | 值 |
|---|---|
| `GEMINI_API_KEY` | 你的 Gemini API key |
| `LARK_APP_ID` | 你的飞书 App ID（`cli_xxx`） |
| `LARK_APP_SECRET` | 你的飞书 App Secret |
| `FEISHU_CHAT_ID` | 你的目标群 `oc_xxx` |

### Step 3：手动拉 bot 进群（一次性）

和 Path A 的 Step 3 第 4 步相同。

### Step 4：启用 Actions 并验证

在你的 fork 的 Actions 标签页，应该看到 `Daily Digest Dispatch` workflow。点它 → "Run workflow" 手动触发一次测试。

如果看到群里收到了测试早报，**完成**。之后每天 UTC 02:30（北京 10:30）自动推送。

### 路径 B 的优缺点

**优点**：
- 零本地依赖，不需要 Mac / 不需要 Python / 不需要 Node.js
- 不需要电脑 7×24 开机
- 云端运行，永远不会"电脑关机就错过"

**缺点**：
- 需要一个 GitHub 账号
- Actions runner 在美国，从美国 IP 访问一些中国源可能偶尔不稳
- 稍微多一些配置步骤（4 个 secrets 要手动填）

---

## 日常使用（两种路径通用）

### 手动跑一次

```bash
cd ~/code/tang-energy-feed
./scripts/run.sh
```

脚本会自动检测环境：
- 如果 `LARK_APP_ID` + `LARK_APP_SECRET` + `FEISHU_CHAT_ID` 都在环境变量里 → 走 **CI 模式**（`scripts/send_lark.py`）
- 否则有 `lark-cli` → 走 **本地模式**（`lark-cli im +messages-send`）
- 都没有 → 报错退出

### 查日志

```bash
# Path A (launchd)
tail -f /tmp/energy-daily-digest.log

# Path B (GitHub Actions)
# 去你 fork 的 Actions 标签页看 workflow runs
```

### 改 config

编辑 `config.json`（Path A）或 GitHub Secrets（Path B）。

---

## 卸载

### Path A
```bash
launchctl unload ~/Library/LaunchAgents/com.tang.energy-daily-digest.plist
rm ~/Library/LaunchAgents/com.tang.energy-daily-digest.plist
rm -rf ~/code/tang-energy-feed
# 可选：rm -rf ~/.config/lark-cli
```

### Path B
- 删掉你 fork 的 repo，或者禁用 Actions

---

## 求助

遇到问题先查 `references/troubleshooting.md`。大部分问题都在那里有答案。

如果**上游 feed** 有问题（`articles=0` 或 `copper=null`），可能是维护者 Tang 那边的 GitHub Actions 出问题了，去 https://github.com/tang730125633/tang-energy-feed/actions 看一下。

## 安全清单（开始前再确认一遍）

- [ ] 没有在戴总/订阅者的电脑上登录 Tang 的 GitHub 账号
- [ ] `git clone` 的 URL 是 `https://` 不是 `git@`（HTTPS 方式不需要登录）
- [ ] Gemini API key 只在 `export` 那一次出现，之后全部用 `$GEMINI_API_KEY` 引用
- [ ] 飞书 App Secret 通过 `lark-cli config init` 存到 `~/.config/lark-cli`，不写到任何文件
- [ ] `config.json` 包含 chat_id，已在 `.gitignore` 中，不会意外 commit
- [ ] bot 已被拉进目标群（否则发送会报 `230001 bot is not in the chat`）
