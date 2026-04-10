# feed-digest.json 数据契约

本文件描述 `tang-energy-feed` 上游 feed 的 JSON 结构。**这是一个契约**：上游和下游都应该遵守这个格式，破坏性修改需要版本号升级。

## 基本结构

```json
{
  "generatedAt": "2026-04-11T22:00:00+00:00",
  "sources": [
    {
      "id": "cpnn.com.cn",
      "name": "电网头条（中国能源传媒集团）",
      "generatedAt": "2026-04-11T22:00:00+00:00",
      "articleCount": 65,
      "hasErrors": false
    }
  ],
  "articles": [
    {
      "id": "cpnn-t20260410_1880328",
      "title": "江苏探索算电协同发展新路径",
      "url": "https://www.cpnn.com.cn/news/dfny/202604/t20260410_1880328.html",
      "summary": "",
      "publishedAt": "2026-04-10",
      "source": "cpnn.com.cn"
    }
  ],
  "copper": {
    "mean_price": "98,440 元/吨",
    "change": "+710 元/吨 ↑",
    "price_range": "98,420-98,460 元/吨",
    "brand": "贵冶、江铜、鲁方等",
    "date": "2026-04-10",
    "raw": {
      "low": "98420",
      "high": "98460",
      "mean": "98440",
      "change": "↑710",
      "unit": "元/吨"
    }
  },
  "stats": {
    "totalArticles": 113,
    "bySource": {
      "cpnn.com.cn": 65,
      "nea.gov.cn": 48
    }
  },
  "errors": [
    {
      "source": "bjx.com.cn",
      "errors": ["Aliyun WAF JS challenge. Day 1 cannot bypass this."]
    }
  ]
}
```

## 字段说明

### 顶层

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `generatedAt` | string (ISO 8601) | ✅ | feed 生成时间（UTC） |
| `sources` | array | ✅ | 每个爬虫的健康状态 |
| `articles` | array | ✅ | 所有去重后的文章（可能为空） |
| `copper` | object / null | ✅ | 铜价数据，null 表示当天爬取失败 |
| `stats` | object | ✅ | 统计信息 |
| `errors` | array | ✅ | 聚合后的所有爬虫错误 |

### articles[] 单条

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 全局唯一 ID，格式 `<source>-<article_id>` |
| `title` | string | ✅ | 文章原标题（未精简，可能 30-60 字） |
| `url` | string | ✅ | 完整文章 URL，必须 http/https 开头 |
| `summary` | string | ⚠️ | v1 为空字符串；v2+ 会填入正文摘要 |
| `publishedAt` | string (ISO date) | ⚠️ | 发布日期，可能为 null |
| `source` | string | ✅ | 源站域名，如 "cpnn.com.cn" |

### copper 对象

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `mean_price` | string | ✅ | 已格式化的均价，如 "98,440 元/吨" |
| `change` | string | ✅ | 已格式化的涨跌，如 "+710 元/吨 ↑" 或 "-1,200 元/吨 ↓" |
| `price_range` | string | ✅ | 已格式化的区间，如 "98,420-98,460 元/吨" |
| `brand` | string | ✅ | 产地牌号，如 "贵冶、江铜、鲁方等" |
| `date` | string | ✅ | 数据日期，格式 YYYY-MM-DD |
| `raw` | object | ⚠️ | 原始数值（数字字符串），不是用来显示的 |

**注意**：cjys.net 不提供升贴水字段，所以 `copper` 里没有 `premium` 字段。

## 版本升级规则

- **允许的变更**（不用升级版本号）：加新字段、加新源到 `sources`、扩展 `stats`
- **破坏性变更**（需要升级版本号）：删字段、改字段类型、改字段名

消费方（例如本 Skill 的 `classify_candidates.py`）应该对**未知字段**保持宽容，对**缺失字段**优雅降级。

## 如果 feed 为空

如果某天 `articles` 是空数组，说明**所有上游爬虫都挂了**。这种情况下本 Skill 应该：

1. 检查 `errors` 字段了解具体原因
2. 不要发送空早报（会让订阅者困惑）
3. 发一条异常通知到群里：`"今日 feed 采集失败，跳过早报推送。errors: ..."`

这种情况理论上不应该发生（cpnn/nea 都挂的概率极低），但要防御。

## 上游 feed 的位置

- **生产 URL**: `https://raw.githubusercontent.com/tang730125633/tang-energy-feed/main/feed/feed-digest.json`
- **仓库地址**: https://github.com/tang730125633/tang-energy-feed
- **爬取频率**: 每天北京时间 06:00
- **可用性**: GitHub 基础设施级别（99.9%+）

## 历史数据

想查看过去任意一天的 feed 快照？用 git history：

```bash
git clone https://github.com/tang730125633/tang-energy-feed.git
cd tang-energy-feed
git log --oneline feed/feed-digest.json
git show <commit>:feed/feed-digest.json
```

这就是"git 作为数据库"的威力。
