# 安装指南（戴总视角）

这份文档假设你是第一次安装这个 Skill。全程大约 **15-20 分钟**。

## 需要准备的东西

- macOS / Linux / WSL 命令行环境
- Python 3.9+
- Node.js 18+
- 一个飞书企业账号（你公司的那个）
- 能在飞书开发者后台创建自建应用的权限

## Step 1：下载 Skill

把 `energy-daily-digest/` 整个目录复制到你电脑上。推荐路径：

```
~/skills/energy-daily-digest/
```

不要放在 iCloud / OneDrive / Google Drive 同步目录下（会和 git 冲突）。

## Step 2：安装 lark-cli

```bash
npm install -g @larksuite/cli
lark-cli --version   # 应该看到版本号
```

## Step 3：配置飞书机器人

**完整步骤**见 `references/lark-setup-guide.md`，**核心要点**：

1. 在 https://open.feishu.cn/app 创建自建应用
2. 开通权限 scope：`im:message:send_as_bot`、`im:chat:read`
3. 运行 `lark-cli config init`，填入 App ID 和 App Secret
4. 把机器人拉进你要发早报的飞书群
5. 查询群的 chat_id：`lark-cli im chats list --as bot`

## Step 4：配置本 Skill

```bash
cd ~/skills/energy-daily-digest
cp config.example.json config.json
```

编辑 `config.json`，把 `oc_REPLACE_WITH_YOUR_GROUP_CHAT_ID` 换成你实际的 chat_id。

保护配置文件：
```bash
echo "config.json" > .gitignore
```

## Step 5：测试整个流程

### 5.1 拉 feed
```bash
python3 scripts/fetch_feed.py config.json > /tmp/feed.json
```
预期 stderr 输出：`✓ Fetched feed: 100+ articles, copper=yes, generated at ...`

### 5.2 分类候选池
```bash
python3 scripts/classify_candidates.py /tmp/feed.json > /tmp/candidates.json
```
预期 stderr 输出：`✓ Classified: top3=X, policy=X, hubei=X, ai_power=X`

### 5.3 查看候选池
```bash
cat /tmp/candidates.json | python3 -m json.tool | less
```

### 5.4 让 AI 从候选池生成 input.json
把 `/tmp/candidates.json` 喂给你的 AI（Claude / GPT 等），用这个指令：

> 请按 `references/selection-rules.md` 的规则从这份 candidates 里挑选并改写成最终的 input.json。严格匹配 `examples/input.sample.json` 的结构：top3=3, policy=3, hubei=2, ai_power=2，每条新闻要有 title/url/summary/impact 四个字段；copper 块直接从 candidates 里搬过来，再写一句 judgment；opportunities 写 4 条 25 字左右的本周关注。输出纯 JSON 到 `/tmp/input.json`。

### 5.5 构建卡片
```bash
python3 scripts/build_card.py /tmp/input.json > /tmp/card.json
```
如果 input.json 格式有问题，脚本会报错并提示。

### 5.6 Dry-run 发送（不真发）
```bash
lark-cli im +messages-send \
  --chat-id "$(python3 -c 'import json; print(json.load(open("config.json"))["feishu"]["chat_id"])')" \
  --as bot \
  --msg-type interactive \
  --content "$(cat /tmp/card.json)" \
  --dry-run
```

如果 dry-run 输出了完整的 API 请求体，说明所有配置都对了。

### 5.7 真实发送
去掉 `--dry-run`，回车。飞书群里应该立即出现一张完整的早报卡片。

**恭喜，Skill 装好了**。

## 日常使用

每天早上想发早报时，只需要跑一次完整流程：

```bash
cd ~/skills/energy-daily-digest
python3 scripts/fetch_feed.py config.json > /tmp/feed.json
python3 scripts/classify_candidates.py /tmp/feed.json > /tmp/candidates.json
# 让 AI 生成 /tmp/input.json
python3 scripts/build_card.py /tmp/input.json > /tmp/card.json
lark-cli im +messages-send \
  --chat-id "$(python3 -c 'import json; print(json.load(open("config.json"))["feishu"]["chat_id"])')" \
  --as bot \
  --msg-type interactive \
  --content "$(cat /tmp/card.json)"
```

大概 1-3 分钟完成，其中 AI 做 remix 占 90% 的时间。

## 设置成每日自动运行（可选）

如果想让早报每天早 7:00 自动发送，可以用 crontab：

```bash
crontab -e
# 加入这一行（替换路径）
0 7 * * * cd ~/skills/energy-daily-digest && ./run.sh
```

但自动化涉及 AI 的无人值守调用，需要额外配置（Claude API / 本地模型等），建议先跑通手动流程后再考虑。

## 卸载

```bash
rm -rf ~/skills/energy-daily-digest
rm -rf ~/.config/lark-cli   # 如果不再使用 lark-cli
```

## 求助

遇到问题先查 `references/troubleshooting.md`。大部分问题都在那里有答案。

如果上游 feed 有问题（`articles=0` 或 `copper=null`），可能是维护者 Tang 那边的 GitHub Actions 出问题了，去 https://github.com/tang730125632/tang-energy-feed/actions 看一下。
