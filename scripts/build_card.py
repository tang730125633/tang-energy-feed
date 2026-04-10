#!/usr/bin/env python3
"""
build_card.py — 将结构化的早报数据转换为飞书 interactive 卡片 JSON。

Usage:
    python3 build_card.py <input.json> > card.json

Input JSON schema: see input_template.json in the same directory.

The output is a complete Feishu card payload (schema 2.0) that can be
passed directly to:
    lark-cli im +messages-send --msg-type interactive --content "$(cat card.json)"

**DO NOT HAND-WRITE THE OUTPUT JSON**. Feishu's card schema is strict
about field names, component structure, and the `table` component's
column bindings. This script is the only supported path.
"""

import json
import sys
from pathlib import Path


def build_news_markdown(index_start: int, items: list) -> str:
    """Render a list of news items as markdown with clickable titles.

    Each item must have {title, url, summary, impact}. The impact line
    is prefixed with 👉 for visual emphasis.
    """
    lines = []
    for i, it in enumerate(items):
        n = index_start + i
        # Escape the leading number so markdown doesn't re-order it.
        # Feishu markdown treats "1." at line start as an ordered list.
        lines.append(f"{n}\\. [{it['title']}]({it['url']})")
        lines.append(it["summary"])
        lines.append(f"👉 {it['impact']}")
        if i < len(items) - 1:
            lines.append("")  # blank line between items
    return "\n".join(lines)


def build_section_header(title: str) -> str:
    return f"**{title}**"


def build_card(data: dict) -> dict:
    """Build the full Feishu interactive card JSON from structured input."""
    date = data["date"]
    sections = data["sections"]

    # ---- section 1-4: news items as markdown blocks ----
    top3_md = build_section_header("一、今日最重要（3条）") + "\n\n" + build_news_markdown(1, sections["top3"])
    policy_md = build_section_header("二、政策与行业（3条）") + "\n\n" + build_news_markdown(4, sections["policy"])
    hubei_md = build_section_header("三、湖北本地（2条）") + "\n\n" + build_news_markdown(7, sections["hubei"])
    ai_power_md = build_section_header("四、AI + 电力（2条）") + "\n\n" + build_news_markdown(9, sections["ai_power"])

    # Main body combines sections 1-4 + the intro line of section 5
    copper_intro = "\n\n" + build_section_header("五、铜价与材料（1条）") + "\n\n11\\. **【长江现货1#铜价】**"
    main_body = top3_md + "\n\n" + policy_md + "\n\n" + hubei_md + "\n\n" + ai_power_md + copper_intro

    # ---- section 5: copper table (native table component) ----
    copper = sections["copper"]
    copper_rows = [
        {"indicator": "1#铜均价", "value": copper["mean_price"]},
        {"indicator": "涨跌", "value": copper["change"]},
        {"indicator": "价格区间", "value": copper["price_range"]},
        {"indicator": "产地牌号", "value": copper["brand"]},
        {"indicator": "日期", "value": copper["date"]},
    ]
    judgment_md = f"👉 **判断**：{copper['judgment']}"

    # ---- section 6: opportunities ----
    opp_lines = [build_section_header("六、重点机会提示"), "", "👉 **本周关注**："]
    for i, opp in enumerate(sections["opportunities"], start=1):
        opp_lines.append(f"{i}\\. {opp}")
    opp_lines.append("")
    opp_lines.append(f"_早报完成时间：{date}_")
    opportunities_md = "\n".join(opp_lines)

    # ---- assemble the card ----
    card = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "style": {
                "text_size": {
                    "normal_v2": {
                        "default": "normal",
                        "pc": "normal",
                        "mobile": "heading",
                    }
                }
            },
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"《零碳能源行业早报｜{date}》",
            },
            "template": "blue",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": main_body},
                {
                    "tag": "table",
                    "page_size": 6,
                    "row_height": "low",
                    "header_style": {
                        "text_align": "left",
                        "text_size": "normal_v2",
                        "background_style": "grey",
                        "text_color": "default",
                        "bold": True,
                        "lines": 1,
                    },
                    "columns": [
                        {
                            "name": "indicator",
                            "display_name": "指标",
                            "width": "auto",
                            "data_type": "text",
                            "horizontal_align": "left",
                        },
                        {
                            "name": "value",
                            "display_name": "数据",
                            "width": "auto",
                            "data_type": "text",
                            "horizontal_align": "left",
                        },
                    ],
                    "rows": copper_rows,
                },
                {"tag": "markdown", "content": judgment_md},
                {"tag": "hr"},
                {"tag": "markdown", "content": opportunities_md},
            ]
        },
    }
    return card


def validate_input(data: dict) -> None:
    """Fail loudly if the input is missing a required field.

    This catches common copy-paste errors from AIs that skip a news item
    or forget the copper block.
    """
    assert "date" in data, "Missing top-level 'date'"
    assert "sections" in data, "Missing top-level 'sections'"
    s = data["sections"]

    required_sections = {
        "top3": 3,
        "policy": 3,
        "hubei": 2,
        "ai_power": 2,
    }
    for key, expected_count in required_sections.items():
        assert key in s, f"Missing section '{key}'"
        assert isinstance(s[key], list), f"Section '{key}' must be a list"
        assert len(s[key]) == expected_count, (
            f"Section '{key}' must have exactly {expected_count} items, "
            f"got {len(s[key])}"
        )
        for i, item in enumerate(s[key]):
            for field in ("title", "url", "summary", "impact"):
                assert field in item and item[field], (
                    f"Section '{key}' item {i} missing field '{field}'. "
                    f"Every news item must have title + url + summary + impact."
                )
            assert item["url"].startswith(("http://", "https://")), (
                f"Section '{key}' item {i}: url must start with http:// or https://, "
                f"got {item['url']!r}"
            )

    assert "copper" in s, "Missing section 'copper'"
    for field in ("mean_price", "change", "price_range", "brand", "date", "judgment"):
        assert field in s["copper"] and s["copper"][field], (
            f"Copper block missing field '{field}'"
        )

    assert "opportunities" in s, "Missing section 'opportunities'"
    assert isinstance(s["opportunities"], list) and len(s["opportunities"]) >= 3, (
        "Opportunities must be a list of at least 3 strings"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python3 build_card.py <input.json> > card.json",
            file=sys.stderr,
        )
        return 2

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    with input_path.open(encoding="utf-8") as f:
        data = json.load(f)

    try:
        validate_input(data)
    except AssertionError as e:
        print(f"Input validation failed: {e}", file=sys.stderr)
        return 1

    card = build_card(data)
    # ensure_ascii=False keeps CJK readable; lark-cli handles UTF-8 fine
    print(json.dumps(card, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
