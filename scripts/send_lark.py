#!/usr/bin/env python3
"""
send_lark.py — zero-dependency Feishu interactive card sender.

Why this exists:
  Our run.sh normally uses `lark-cli` to send the final card to Feishu.
  That's great for local development. But for CI environments (GitHub
  Actions, Cron on a server), installing Node.js + lark-cli is wasteful
  when the only thing we need is "POST a JSON card to one Feishu group".

  This script does exactly that, using only Python stdlib (urllib).

Credentials — all via environment variables (never hardcoded):
  LARK_APP_ID         (required) Feishu self-built app ID (cli_xxx)
  LARK_APP_SECRET     (required) Feishu self-built app secret
  FEISHU_CHAT_ID      (required) target group chat ID (oc_xxx)

Usage:
  python3 send_lark.py <path/to/card.json>

The card.json file must be a valid Feishu interactive card schema 2.0
payload — exactly what scripts/build_card.py produces.

Exit codes:
  0 = success
  1 = API error, bad credentials, or network error
  2 = bad input arguments
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


FEISHU_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)
FEISHU_MESSAGE_URL = (
    "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
)


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """Exchange app credentials for a 2-hour tenant access token."""
    body = json.dumps(
        {"app_id": app_id, "app_secret": app_secret}
    ).encode("utf-8")

    req = urllib.request.Request(
        FEISHU_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore") if e.fp else ""
        raise SystemExit(
            f"HTTP {e.code} from Feishu auth API: {e.reason}\n"
            f"Response: {err[:500]}"
        )
    except urllib.error.URLError as e:
        raise SystemExit(f"Network error reaching Feishu auth API: {e.reason}")

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"Feishu auth returned non-JSON: {raw[:500]}")

    if result.get("code") != 0:
        raise SystemExit(
            f"Feishu auth failed (code={result.get('code')}): "
            f"{result.get('msg', 'unknown error')}\n"
            f"Hint: check that LARK_APP_ID and LARK_APP_SECRET are correct, "
            f"and that the app has im:message:send_as_bot scope enabled."
        )

    token = result.get("tenant_access_token", "")
    if not token:
        raise SystemExit(f"Feishu auth response missing token: {result}")

    return token


def send_interactive_card(
    token: str, chat_id: str, card: dict
) -> dict:
    """POST an interactive card to a Feishu group.

    Important: Feishu's API expects `content` to be a JSON-STRING (the card
    JSON, serialized again). This is a common pitfall — don't send it as
    a dict, it will be rejected with a schema error.
    """
    body = json.dumps(
        {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        FEISHU_MESSAGE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore") if e.fp else ""
        raise SystemExit(
            f"HTTP {e.code} from Feishu message API: {e.reason}\n"
            f"Response: {err[:500]}"
        )
    except urllib.error.URLError as e:
        raise SystemExit(
            f"Network error reaching Feishu message API: {e.reason}"
        )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"Feishu message API returned non-JSON: {raw[:500]}")

    if result.get("code") != 0:
        code = result.get("code")
        msg = result.get("msg", "unknown")
        hints = {
            230001: "bot is not in the target chat — pull the bot into the group first",
            230002: "bot lacks permission to send to this chat",
            99991663: "invalid access token — check app credentials",
        }
        hint = hints.get(code, "")
        raise SystemExit(
            f"Feishu message send failed (code={code}): {msg}"
            + (f"\nHint: {hint}" if hint else "")
        )

    return result


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python3 send_lark.py <card.json>",
            file=sys.stderr,
        )
        return 2

    card_path = Path(sys.argv[1])
    if not card_path.exists():
        print(f"Card file not found: {card_path}", file=sys.stderr)
        return 2

    # All three env vars are required
    app_id = os.environ.get("LARK_APP_ID", "").strip()
    app_secret = os.environ.get("LARK_APP_SECRET", "").strip()
    chat_id = os.environ.get("FEISHU_CHAT_ID", "").strip()

    missing = [
        name
        for name, val in [
            ("LARK_APP_ID", app_id),
            ("LARK_APP_SECRET", app_secret),
            ("FEISHU_CHAT_ID", chat_id),
        ]
        if not val
    ]
    if missing:
        print(
            "Missing environment variables: " + ", ".join(missing) + "\n"
            "\n"
            "These must be set either:\n"
            "  a) In GitHub Actions: Settings → Secrets → Actions\n"
            "  b) Locally: export LARK_APP_ID=cli_xxx ; export LARK_APP_SECRET=xxx ; "
            "export FEISHU_CHAT_ID=oc_xxx\n"
            "\n"
            "How to get these values:\n"
            "  LARK_APP_ID / LARK_APP_SECRET: https://open.feishu.cn/app → "
            "your app → 凭证与基础信息\n"
            "  FEISHU_CHAT_ID: run `lark-cli im chats list --as bot` and "
            "copy the oc_xxx of your target group\n",
            file=sys.stderr,
        )
        return 1

    # Load the card JSON
    try:
        with card_path.open(encoding="utf-8") as f:
            card = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Card file is not valid JSON: {e}", file=sys.stderr)
        return 2

    print(
        f"→ Requesting tenant_access_token for app {app_id[:12]}...",
        file=sys.stderr,
    )
    token = get_tenant_access_token(app_id, app_secret)
    print(f"✓ Got token ({len(token)} chars)", file=sys.stderr)

    print(
        f"→ Sending interactive card to {chat_id[:12]}...",
        file=sys.stderr,
    )
    result = send_interactive_card(token, chat_id, card)

    data = result.get("data", {})
    message_id = data.get("message_id", "unknown")
    print(f"✓ Sent successfully. message_id={message_id}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
