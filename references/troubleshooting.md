# Troubleshooting — 常见故障排查

按"症状 → 诊断 → 解决"组织。大部分问题都在这里能找到答案。

---

## 1. fetch_feed.py 阶段的问题

### 症状：`Network error fetching feed: <reason>`
**诊断**：到 `raw.githubusercontent.com` 的网络不通。国内偶发性 GitHub 访问慢。

**解决**：
1. 手动 curl 测试：`curl -I https://raw.githubusercontent.com/tang730125633/tang-energy-feed/main/feed/feed-digest.json`
2. 如果超时，设置代理：`export https_proxy=http://127.0.0.1:7890`（按你本地代理端口）
3. 或用 fastgit 镜像：把 config.json 的 feed_url 改成 `https://raw.fastgit.org/tang730125633/tang-energy-feed/main/feed/feed-digest.json`
4. 本地离线测试：把 feed_url 设为本地文件路径，如 `/Users/xxx/feed-digest.json`

### 症状：`Feed validation failed: Feed missing top-level fields: ['copper']`
**诊断**：上游 feed schema 变了，或者今天铜价爬取失败。

**解决**：
1. 去 https://github.com/tang730125633/tang-energy-feed/tree/main/feed 看原始 feed-digest.json
2. 如果字段缺失，可能需要更新 `classify_candidates.py` 的 schema 兼容逻辑
3. 联系上游维护者（Tang）

### 症状：`Warning: feed has zero articles`
**诊断**：上游所有爬虫今天都挂了（极其罕见）。

**解决**：
- 不要发送早报（发个空的会让订阅者困惑）
- 查 feed 的 `errors` 字段了解原因
- 等下次 cron 运行（明天早 6:00）

---

## 2. classify_candidates.py 阶段的问题

### 症状：某个 section 的候选数为 0
**诊断**：当天的新闻主题碰巧没匹配到该板块的关键词。

**解决**：
- `ai_power` 为 0 是最常见的——当天没算电协同新闻。可以放宽：从 `policy` 或 `top3` 池里借 2 条含"数据中心"、"算力"、"智慧"的
- `hubei` 为 0：见下一条

### 症状：hubei 候选池为 0
**诊断**：当天既没有湖北本地新闻，也没有周边省份新闻。

**解决**：
1. 检查 feed.articles 里手动搜"湖北"、"武汉"、"湖南"等关键词
2. 如果真的为 0，这是极罕见情况。应急方案：
   - 从 feed.articles 里随便挑 2 条全国级新闻
   - 在 `impact` 字段里加一句"湖北相关市场同步跟踪"
   - **仍然保留"三、湖北本地"的板块标题**
3. 告诉上游维护者，加强 hubei 爬取源

---

## 3. AI remix 阶段的问题

### 症状：build_card.py 报 `Section 'top3' must have exactly 3 items, got 2`
**诊断**：AI 挑少了。

**解决**：回去挑满 3 条。即使质量一般也要挑满，不能缺。

### 症状：build_card.py 报 `item N: url must start with http:// or https://`
**诊断**：AI 在改写时把 URL 弄丢了/编造了假 URL。

**解决**：**绝对不要编造 URL**。从 candidates.json 里复制原 URL。如果 url 为空字符串，这条新闻本身就有问题，换一条。

### 症状：AI 把湖北板块改成了"区域动态"
**诊断**：违反了硬规则。

**解决**：标题永远是"三、湖北本地"，内容可以是湖北周边，但标题不能动。重新生成。

---

## 4. lark-cli 发送阶段的问题

### 症状：`{"code": 230001, "msg": "bot is not in the chat"}`
**诊断**：bot 不在目标群里。

**解决**：
1. 打开飞书群 → 群设置 → 群机器人 → 添加机器人 → 选择你的机器人
2. 或者用 API 拉入：`lark-cli im +chat-members-create --chat-id oc_xxx --user-ids <bot_open_id>`
3. 拉入后用 `lark-cli im chats list --as bot` 确认能看到该群

### 症状：`{"code": 99991663, "msg": "invalid access token"}`
**诊断**：App ID / Secret 错了或 scope 不足。

**解决**：
1. 检查 `lark-cli auth status`
2. 去飞书开发者后台确认应用凭证
3. 确认权限 scope 里勾选了 `im:message:send_as_bot`
4. 重新发布应用版本

### 症状：消息发出去了但卡片显示"当前客户端暂不支持该消息"
**诊断**：飞书客户端版本太老，不支持 schema 2.0 的 interactive 卡片。

**解决**：让接收方升级飞书客户端到最新版（手机 + 桌面端都要升级）。

### 症状：卡片显示了但铜价表格变成了纯文本
**诊断**：`table` 组件在某些老版本飞书里不渲染，或者卡片 schema 被改错了。

**解决**：
1. 检查 `/tmp/card.json` 里有没有 `"tag": "table"`
2. 不要手写卡片 JSON，用 `build_card.py`
3. 确认接收方飞书客户端版本 >= 7.0

---

## 5. 身份问题

### 症状：消息显示为"用户名"发送，不是 bot
**诊断**：错用了 `--as user`。

**解决**：**早报必须 `--as bot`**。这是硬规则。如果某条命令忘了加 `--as bot`，立即撤回消息并重发：
```bash
lark-cli im messages delete --message-id <om_xxx> --as bot
```

---

## 6. 数据质量问题

### 症状：爬到的湖北新闻是企业软文
**诊断**：cpnn.com.cn 偶尔会收录企业通稿。

**解决**：在 AI remix 阶段，手动过滤掉标题含 "XX 公司"、"XX 集团" 开头的企业新闻，优先选官方机构主语的新闻。

### 症状：铜价数据是好几天前的
**诊断**：周末/节假日铜价不更新是正常的（长江有色只在工作日更新）。

**解决**：
- 周一早上可能显示的是周五的数据，这是正常的
- 在 `copper.judgment` 里注明"数据截至上一交易日"
- 如果工作日也没更新，联系上游维护者

---

## 7. 通用排查思路

出问题时按这个顺序查：

```
1. 手动访问 feed URL → 确认上游 feed 是否正常
2. 跑 fetch_feed.py → 确认能拿到 JSON
3. 跑 classify_candidates.py → 确认候选池不空
4. 手动看 candidates.json → 理解为什么某个板块为空
5. 跑 build_card.py → 确认 input.json 格式对
6. dry-run lark-cli（加 --dry-run）→ 确认请求体对
7. 真发 → 看返回码
```

每一步都能独立验证，不要一次跑全流程。
