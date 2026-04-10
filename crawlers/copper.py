#!/usr/bin/env python3
"""
Crawler for 长江现货铜价 (cjys.net/price).

This is the most reliable copper price source we've found:
- No WAF, no JS rendering required
- Prices are in plain <table> rows
- Updates on every trading day

Output shape matches what zero-carbon-daily-report's build_card.py expects,
so the daily report skill can consume this JSON directly.
"""

from __future__ import annotations

import re
import sys
import traceback

from common import (
    clean_text,
    emit,
    fetch_html,
    utc_now_iso,
)

SOURCE = "cjys.net"
SOURCE_NAME = "长江有色金属现货报价"
BASE_URL = "https://www.cjys.net/price"


def empty_copper_feed(error: str = "") -> dict:
    return {
        "source": SOURCE,
        "sourceName": SOURCE_NAME,
        "generatedAt": utc_now_iso(),
        "copper": None,
        "errors": [error] if error else [],
    }


def crawl() -> dict:
    html = fetch_html(BASE_URL)

    # The target row looks like:
    # <tr><td>长江 1#电解铜</td><td>98420</td><td>98460</td><td>元/吨</td>
    # <td>98440</td><td><font color="red">↑710</font></td>
    # <td>贵冶、江铜、鲁方等</td><td>-</td><td>2026-04-10</td></tr>
    row_pattern = re.compile(
        r"<tr[^>]*>(.*?1#电解铜.*?)</tr>",
        re.IGNORECASE | re.DOTALL,
    )
    m = row_pattern.search(html)
    if not m:
        return empty_copper_feed("Copper row not found in cjys.net HTML")

    row_html = m.group(1)
    # Pull all <td>...</td> cells
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
    if len(cells) < 9:
        return empty_copper_feed(
            f"Copper row has {len(cells)} cells, expected >= 9"
        )

    # Strip tags inside each cell (e.g. <font color="red">↑710</font>)
    def strip(s: str) -> str:
        s = re.sub(r"<[^>]+>", "", s)
        return clean_text(s)

    cells = [strip(c) for c in cells]
    # Expected layout:
    # [0] 品名        "长江 1#电解铜"
    # [1] 最低价      "98420"
    # [2] 最高价      "98460"
    # [3] 单位        "元/吨"
    # [4] 均价        "98440"
    # [5] 涨跌        "↑710"
    # [6] 产地牌号    "贵冶、江铜、鲁方等"
    # [7] 交货地      "-"
    # [8] 日期        "2026-04-10"

    low, high = cells[1], cells[2]
    unit = cells[3]
    mean_raw = cells[4]
    change_raw = cells[5]
    brand = cells[6]
    date = cells[8]

    # Format mean_price with thousands separator
    try:
        mean_formatted = f"{int(mean_raw):,} {unit}"
    except ValueError:
        mean_formatted = f"{mean_raw} {unit}"

    # Format change: "↑710" → "+710 元/吨 ↑", "↓1200" → "-1,200 元/吨 ↓"
    change_formatted = change_raw
    if change_raw:
        up = "↑" in change_raw
        down = "↓" in change_raw
        num = re.sub(r"[↑↓\s]", "", change_raw)
        try:
            n = int(num)
            sign = "+" if up else ("-" if down else "")
            arrow = " ↑" if up else (" ↓" if down else "")
            change_formatted = f"{sign}{n:,} {unit}{arrow}"
        except ValueError:
            pass

    # Format price range
    try:
        range_formatted = f"{int(low):,}-{int(high):,} {unit}"
    except ValueError:
        range_formatted = f"{low}-{high} {unit}"

    copper = {
        "mean_price": mean_formatted,
        "change": change_formatted,
        "price_range": range_formatted,
        "brand": brand,
        "date": date,
        "raw": {
            "low": low,
            "high": high,
            "mean": mean_raw,
            "change": change_raw,
            "unit": unit,
        },
    }

    return {
        "source": SOURCE,
        "sourceName": SOURCE_NAME,
        "generatedAt": utc_now_iso(),
        "copper": copper,
        "errors": [],
    }


if __name__ == "__main__":
    try:
        emit(crawl())
    except Exception as e:  # noqa: BLE001
        emit(empty_copper_feed(f"{type(e).__name__}: {e}"))
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(0)
