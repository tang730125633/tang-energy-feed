# 发给戴总的 AI 的安装引导提示词

下面这段是用户（戴总）**复制粘贴**发给他的 AI（OpenClaw / Claude Code / Cursor / 其他）的完整消息。

---

## 📋 复制从这里开始 ⬇

```
你好，请帮我安装并运行一个**零碳能源行业早报自动化系统**。

## 需求
我要让我的电脑每天早上 10:30 自动把当天的中国能源行业新闻（含长江铜价）
生成一份结构化的早报，并推送到我指定的飞书群里。我本人只做"视觉审核"，
不想自己打开终端跑任何命令。

## 参考仓库（这是整个 Skill 的源头）
https://github.com/tang730125633/tang-energy-feed

这是一个 public repo，作者 Tang 已经把完整的安装流程、脚本、AI prompt、
归档系统、定时任务模板全部打包好了，仓库根目录有一份 `SKILL.md` 文件，
里面对齐了 Zara Zhang Rui 的 follow-builders 设计模式，包含 9 步
onboarding。

## 我希望你现在立刻做的事（按顺序）

### 第 1 步：读 SKILL.md 理解系统原理

用你的 WebFetch 或等效工具读这个 URL 的内容:

    https://raw.githubusercontent.com/tang730125633/tang-energy-feed/main/SKILL.md

完整读完之后，**不要立刻执行任何命令**。先回答我 5 个问题：

1. **这个 Skill 在我电脑上要创建哪些文件夹？每个文件夹是干什么的？**
   （我要知道它会在我硬盘上留下什么痕迹，避免以后找不到为什么用不了）

2. **归档系统在哪里？它归档什么内容？为什么需要归档？**
   （我想知道这部分能不能人工干预）

3. **早报的主要执行脚本是哪几个？它们依次做什么？**
   （我要能看懂主流程，而不是被黑盒子控制）

4. **工作原理是什么？每天早上 10:30 我应该期待看到什么效果？**
   （如果出问题，我要能自己初步判断是哪一环）

5. **核心模板/prompt 文件在哪里？我如果想自己调 AI 的输出风格，改哪些文件？**
   （保留给我 human-in-the-loop 的控制权）

### 第 2 步：等我确认"OK，原理清楚了"

在我明确说"OK，原理清楚了"或"继续"之前，**不要** clone repo、**不要**
创建任何文件夹、**不要**修改我的 shell 配置、**不要**装定时任务。

### 第 3 步：开始 9 步 onboarding（我确认后才进入）

SKILL.md 的 `## First Run — Onboarding` 章节有 9 步详细引导。请严格按照
这 9 步来，每一步都问我一个具体问题，等我回答再进入下一步。**不要一次性
问我 4 个问题**——follow-builders 的做法是一步一问，体验更顺。

需要我回答的问题包括（按 SKILL.md 定义的顺序）：
- Step 2: 定时触发时间（默认 10:30，我想改就改）
- Step 3: 目标飞书群 chat_id
- Step 4: AI 模型（默认 gemini-3-flash-preview）
- Step 5: Gemini API key 和飞书 bot 凭据如何设置

### 第 4 步：配置凭据（两个都是我自己操作，你不碰 key）

这两样**我会自己在终端里配置**，你绝对不要试图读、写、或粘贴这些凭据的真
实值:

1. **Gemini API Key**
   - 我去 https://aistudio.google.com/apikey 免费申请
   - 在我自己的终端运行:
       echo 'export GEMINI_API_KEY="我复制的key"' >> ~/.zshrc
       source ~/.zshrc
   - 配好我告诉你 "done"

2. **飞书 Bot 凭据**
   - 我去 https://open.feishu.cn/app 创建自建应用
   - 开通 scope `im:message:send_as_bot`
   - 把机器人手动拉进我的目标飞书群
   - 在我的终端运行 `lark-cli config init` 交互式填入 App ID / App Secret
   - 配好我告诉你 "done"

### 第 5 步：安装定时任务

读 SKILL.md 的 `## 2. First Run — Onboarding` 的 `Step 8: Set Up Cron /
launchd / OpenClaw cron` 部分，根据我的操作系统选一个方案。

我用的是 **macOS + OpenClaw**，所以**优先用 OpenClaw 自带的 cron 机制**
来调度（对应 SKILL.md 里的 OpenClaw 分支）。如果 OpenClaw 没有 cron 功能，
fallback 到 launchd（仓库里有 `launchd/install.sh` 一键脚本）。

**关键**：定时触发的命令必须带 `--production` 参数，不能带 `--test`。
即:
    bash ~/code/tang-energy-feed/scripts/run.sh --production

### 第 6 步：立刻发一份测试早报

配置完成后，在当前对话里立刻跑一次:

    cd ~/code/tang-energy-feed && bash scripts/run.sh --test

**注意是 --test，不是 --production**。这会真实发送到我的飞书群，让我
视觉审核卡片效果，但**不会**污染 `.last-sent-date` 或 `archive/` 目录
——这样明天早上 10:30 的第一次正式自动推送才能正常运行。

### 第 7 步：告诉我验证方式

告诉我：
- 明天早上 10:30 之后，我应该去哪里看日志确认定时任务成功跑了？
- 如果失败了，我应该查哪个文件或跑哪条命令排错？
- 我随时想手动触发一次，应该怎么操作（一句话给我就行，我直接发给你）？

## 我的 5 条原则（请你严格遵守）

1. **透明**：在你执行任何创建文件夹 / 改配置 / 装定时任务的操作之前，
   先把"你即将做什么"告诉我。我同意了你才做。

2. **可复用**：每一个创建的文件都要告诉我用途，这样我以后能自己修改或复用。

3. **可排错**：告诉我原理，这样如果哪天系统挂了，我能自己初步判断问题。

4. **可干预**：告诉我哪些是"模板/prompt"文件（AI 的大脑），如果我想调
   输出风格，应该改哪些文件。

5. **不碰凭据**：GEMINI_API_KEY、LARK_APP_SECRET 这些东西你永远不碰。
   我自己在终端里配置，配完告诉你 "done"。

## 我的硬规则（来自 SKILL.md，不可协商）

- 发送身份必须是 `--as bot`（不是 user）
- 消息类型必须是 `interactive` 卡片
- 铜价必须用飞书原生 `table` 组件（不是 markdown 表格，不是 code_block）
- 6 板块固定，标题一字不改：
  一、今日最重要（3条）/ 二、政策与行业（3条）/ 三、湖北本地（2条）/
  四、AI + 电力（2条）/ 五、铜价与材料（1条）/ 六、重点机会提示

## 开始吧

现在请立刻读 SKILL.md 并回答我 5 个问题。**读完再说话，不要边读边做事**。
```

## 📋 复制到这里结束 ⬆

---

## 使用说明

- 这段话设计成戴总**复制粘贴一次**就能让 AI 完整理解的格式
- 关键设计：**先读懂 → 再回答问题 → 再等确认 → 再执行**
  （防止 AI 一上来就 clone 各种东西让戴总懵）
- 强调 5 条原则 + 6 条硬规则，保证 AI 行为可预期
- 所有凭据动作都明确由戴总自己做，AI 不碰 key
- test vs production 区分写得很清楚，避免第一次运行就污染归档
