<p align="center">
  <img src="./assets/readme/hero-zel-v1.webp" width="100%" alt="Zel and the orange cat reviewing energy sources, copper signals, daily stories, and visible source failures">
</p>

# tang-energy-feed

把能源新闻与长江现货铜价整理成可消费的 JSON feed；下游可以先验证数据，再选择在本地或 GitHub Actions 中生成并推送飞书早报。

## 先看可核验的证据

- [直接订阅 live JSON feed](https://raw.githubusercontent.com/tang730125633/tang-energy-feed/main/feed/feed-digest.json)；仓库中的 [当前快照](./feed/feed-digest.json) 同时给出 `generatedAt`、`sources`、`stats`、`errors` 与 `copper`。
- [采集 workflow](./.github/workflows/daily-crawl.yml) 定义了定时与手动触发、聚合、摘要补充、质量检查，以及仅在 feed 变更时提交的路径。
- [云端派发 workflow](./.github/workflows/daily-digest.yml) 定义了从 feed 到飞书卡片的独立消费路径与所需 secrets。

这些链接是接口与工作流的证据，不等同于“每一次运行都成功”。订阅或推送前，请检查目标分支的 Actions 记录与 feed 自身的 `errors`。

## 机制：发布与消费分开

```text
能源新闻源 + 长江铜价
        ↓
crawlers → aggregate → feed/feed-digest.json
        ↓                         ↓
本地脚本 / 其他程序            飞书消费管道
```

采集端把每个源的时间、文章数与错误保留在 JSON 中；消费端读取统一结构，再进行候选筛选、AI remix、飞书 interactive card 构造与发送。中部专题使用同一份聚合数据的 [feed-central-energy.json](./feed/feed-central-energy.json) 子集。

### 降级语义

- 单个来源失败不会被伪装成“健康”：聚合结果保留来源级 `hasErrors` 与 `articleCount`。
- [质量检查](./scripts/quality_check.sh) 会在文章少于 30 篇或缺失铜价时返回警告；当前采集 workflow 将该警告记录下来后继续执行，因此消费者仍应自行判定该次 feed 是否可用。
- `copper: null`、空文章列表或 `errors` 非空都应被视为降级信号，而不是可直接发送的早报。

## 三个入口

### 1. 直接订阅

将以下 URL 放入你的脚本、Agent 或数据工具；它始终指向 `main` 的最新提交快照：

```text
https://raw.githubusercontent.com/tang730125633/tang-energy-feed/main/feed/feed-digest.json
```

### 2. 本地验证

克隆后可先只检查仓库内的 feed，不会发送消息、写归档或调用模型：

```bash
git clone https://github.com/tang730125633/tang-energy-feed.git
cd tang-energy-feed
bash scripts/quality_check.sh feed/feed-digest.json
```

要配置本地消费端，继续运行 `./scripts/setup.sh`，并在真正发送前阅读 [预检脚本](./scripts/preflight.sh) 的检查范围。

### 3. 云端推送到飞书

Fork 后，在 Actions secrets 中配置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`LARK_APP_ID`、`LARK_APP_SECRET` 与 `FEISHU_CHAT_ID`，再启用 [daily-digest workflow](./.github/workflows/daily-digest.yml)。它会生成临时配置并调用 `scripts/run.sh`。

> 这条路径会向真实飞书群发送内容。先用手动 `workflow_dispatch` 核验目标群和卡片，且仅在负责运营者明确授权后启用定时派发。

## 首次使用时要知道

- 发送身份被限定为 bot；密钥只通过环境变量或 GitHub secrets 传入，不写入 `config.json`。
- `scripts/run.sh --test` 会真的发送飞书卡片，但不写归档、去重缓存或 `.last-sent-date`；它不是“无副作用预览”。
- `scripts/run.sh --production` 才会执行归档、滚动去重与当日幂等跳过。详情见 [SKILL.md](./SKILL.md) 与 [INSTALL.md](./INSTALL.md)。

<details>
<summary>实现细节与扩展入口</summary>

- [数据契约](./references/data-contract.md) 定义 feed 结构；[筛选规则](./references/selection-rules.md) 定义候选处理。
- [build_card.py](./scripts/build_card.py) 使用飞书 schema 2.0 的 interactive card 与原生 table 组件承载铜价数据。
- [launchd](./launchd/) 提供本地定时模板；云端场景只需使用 `daily-digest.yml`。
</details>

## License

MIT © 2026 Tang ([tang730125633](https://github.com/tang730125633))
