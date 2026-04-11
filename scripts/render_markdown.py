#!/usr/bin/env python3
"""
render_markdown.py — Render an input.json (AI remix output) as a
human-readable Markdown file.

This is called by archive.py as part of the post-send archival step.
The resulting .md file is committed to archive/YYYY/MM/YYYY-MM-DD.md
and can be previewed directly on GitHub (which auto-renders Markdown),
making it trivially browsable without running any code.

Usage:
    python3 render_markdown.py <input.json> [meta.json] > output.md

If meta.json is supplied, its fields are included in a YAML-ish frontmatter
block at the top of the output. Missing meta is OK — we still produce a
valid Markdown file.

Input JSON shape: same as scripts/build_card.py expects — see
examples/input.sample.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def render_meta_block(meta: dict) -> list[str]:
    """Render an optional metadata block as a GitHub-friendly blockquote."""
    if not meta:
        return []
    lines = ["> **归档元数据**"]
    for key, label in [
        ("date", "早报日期"),
        ("sentAt", "发送时间"),
        ("messageId", "飞书消息 ID"),
        ("chatId", "目标群 ID"),
        ("model", "AI 模型"),
        ("feedGeneratedAt", "Feed 生成时间"),
        ("feedTotalArticles", "Feed 文章总数"),
        ("articlesUsed", "早报采用条数"),
    ]:
        if key in meta and meta[key] is not None:
            lines.append(f"> - **{label}**: `{meta[key]}`")
    lines.append("")
    return lines


def render_news_section(
    header: str, items: list[dict], start_index: int
) -> list[str]:
    """Render a group of news items. `start_index` is the first item number."""
    lines = [f"## {header}", ""]
    for i, item in enumerate(items):
        n = start_index + i
        title = item.get("title", "(无标题)")
        url = item.get("url", "#")
        summary = item.get("summary", "")
        impact = item.get("impact", "")
        lines.append(f"**{n}. [{title}]({url})**")
        if summary:
            lines.append("")
            lines.append(summary)
        if impact:
            lines.append("")
            lines.append(f"> 👉 {impact}")
        lines.append("")
    return lines


def render_copper_section(copper: dict) -> list[str]:
    """Render the copper price section with a real Markdown table."""
    lines = [
        "## 五、铜价与材料（1条）",
        "",
        "**11. 【长江现货1#铜价】**",
        "",
        "| 指标 | 数据 |",
        "|:---|:---|",
        f"| 1#铜均价 | {copper.get('mean_price', '—')} |",
        f"| 涨跌 | {copper.get('change', '—')} |",
        f"| 价格区间 | {copper.get('price_range', '—')} |",
        f"| 产地牌号 | {copper.get('brand', '—')} |",
        f"| 日期 | {copper.get('date', '—')} |",
        "",
    ]
    judgment = copper.get("judgment", "")
    if judgment:
        lines.append(f"> 👉 **判断**: {judgment}")
        lines.append("")
    return lines


def render_opportunities(opps: list[str]) -> list[str]:
    lines = ["## 六、重点机会提示", "", "**本周关注:**", ""]
    for i, opp in enumerate(opps, start=1):
        lines.append(f"{i}. {opp}")
    lines.append("")
    return lines


def render_markdown(data: dict, meta: dict | None = None) -> str:
    """Render the full daily report as a Markdown document."""
    date = data.get("date", "unknown")
    sections = data.get("sections", {})

    lines: list[str] = []

    # Title
    lines.append(f"# 《零碳能源行业早报｜{date}》")
    lines.append("")

    # Metadata block (if provided)
    lines.extend(render_meta_block(meta or {}))

    # News sections
    lines.extend(render_news_section(
        "一、今日最重要（3条）", sections.get("top3", []), start_index=1
    ))
    lines.extend(render_news_section(
        "二、政策与行业（3条）", sections.get("policy", []), start_index=4
    ))
    lines.extend(render_news_section(
        "三、湖北本地（2条）", sections.get("hubei", []), start_index=7
    ))
    lines.extend(render_news_section(
        "四、AI + 电力（2条）", sections.get("ai_power", []), start_index=9
    ))

    # Copper (special formatting with Markdown table)
    copper = sections.get("copper", {})
    if copper:
        lines.extend(render_copper_section(copper))

    # Opportunities
    opps = sections.get("opportunities", [])
    if opps:
        lines.extend(render_opportunities(opps))

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        "*由 [tang-energy-feed]"
        "(https://github.com/tang730125633/tang-energy-feed) 自动生成与归档。*"
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(
            "Usage: python3 render_markdown.py <input.json> [meta.json] > output.md",
            file=sys.stderr,
        )
        return 2

    input_path = Path(sys.argv[1])
    meta_path = Path(sys.argv[2]) if len(sys.argv) == 3 else None

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    with input_path.open(encoding="utf-8") as f:
        data = json.load(f)

    meta = None
    if meta_path and meta_path.exists():
        with meta_path.open(encoding="utf-8") as f:
            meta = json.load(f)

    markdown = render_markdown(data, meta)
    sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
