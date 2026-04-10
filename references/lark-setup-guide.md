# 飞书机器人配置指南（戴总视角）

如果这是你第一次使用 `lark-cli` 发送飞书消息，按下面的步骤走一遍。**全程不到 15 分钟**。

## 前置要求

- macOS / Linux / WSL
- Node.js 18+（lark-cli 需要）
- 一个飞书企业账号（你在公司的那个就行）
- 管理员权限（能在开发者后台创建应用）

## Step 1：安装 lark-cli

```bash
npm install -g @larksuite/cli
```

验证安装：
```bash
lark-cli --version
```

应该看到版本号如 `1.0.7`。

## Step 2：在飞书开发者后台创建一个自建应用

1. 打开 https://open.feishu.cn/app
2. 点击"创建企业自建应用"
3. 填写应用名称（如 `"能源早报机器人"`）、描述、图标
4. 创建后进入应用详情页

## Step 3：获取 App ID 和 App Secret

在应用的"凭证与基础信息"页面，你会看到：
- `App ID`：以 `cli_` 开头的字符串
- `App Secret`：一串随机字符

**这两个值接下来要填到 lark-cli 配置里，但不要发到任何聊天工具、文档、git 仓库里**。

## Step 4：配置 lark-cli

```bash
lark-cli config init
```

按提示填入 App ID 和 App Secret。配置会存在 `~/.config/lark-cli/` 下（macOS/Linux）。

验证配置：
```bash
lark-cli auth status
```

## Step 5：开通必要的权限 Scope

在飞书开发者后台 → 你的应用 → "权限管理"，勾选以下 scope：

**必选**：
- `im:message:send_as_bot` — 以机器人身份发消息
- `im:chat:read` — 读群列表（查 chat_id 用）

**推荐**：
- `im:chat.members:read` — 读群成员（可用于调试）

勾选后点"版本管理与发布"，提交审核（个人应用一般秒过）。

## Step 6：把机器人拉进目标群

1. 打开飞书，进入你想发早报的群
2. 群设置 → 群机器人 → 添加机器人 → 找到你创建的"能源早报机器人" → 添加

**⚠️ 重要**：bot 必须是群成员才能发消息。如果发送时报 `"bot is not in the chat"`，说明这一步没做。

## Step 7：查询 chat_id

```bash
lark-cli im chats list --as bot
```

返回类似：
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "chat_id": "oc_xxxxxxxxxxxxxxxx",
        "name": "你的群名",
        ...
      }
    ]
  }
}
```

复制目标群的 `chat_id`（以 `oc_` 开头）。

## Step 8：填入 config.json

回到 energy-daily-digest skill 目录：

```bash
cp config.example.json config.json
```

编辑 `config.json`，把 `oc_REPLACE_WITH_YOUR_GROUP_CHAT_ID` 替换成你上一步拿到的 chat_id。

**重要**：
- `config.json` 不要提交到 git
- 在 skill 目录下加一个 `.gitignore`，内容只要一行 `config.json`

## Step 9：测试发送一条消息

```bash
lark-cli im +messages-send \
  --chat-id "$(jq -r .feishu.chat_id config.json)" \
  --as bot \
  --text "Hello from energy-daily-digest skill!"
```

如果群里收到了这条消息，**全部配置完成**。

## 常见报错

### `"bot is not in the chat"`

bot 没被拉进群。回到 Step 6。

### `"invalid access token"` 或 `99991663`

App ID / Secret 错了，或者权限 scope 没开通。回到 Step 3 和 Step 5 检查。

### 发送 interactive 卡片时返回 `"invalid content"`

卡片 JSON 结构错了。**永远不要手写卡片 JSON**，用 `scripts/build_card.py` 生成。

## 安全提醒

- **永远不要把 App Secret 或 access token 粘贴到聊天工具里**（包括发给 AI）
- 配置好之后，`~/.config/lark-cli/` 下的文件不要分享、不要上传到云盘、不要 git commit
- 如果怀疑泄漏，立即去开发者后台"凭证与基础信息"页面**重置 App Secret**

---

配好之后你会发现：**发送早报只剩一个步骤**—— 跑一下 Skill 的流程，卡片自动出现在群里。享受第三代架构带来的简单吧。
