#!/usr/bin/env python3
"""
ai_remix.py — Call an OpenAI-compatible LLM to remix candidates into input.json.

This is the ONLY script in the whole pipeline that needs an LLM. Everything
else (fetch, classify, build_card) is deterministic.

Supports any OpenAI-compatible endpoint via config.json's `ai` block:
  - Gemini (default):  https://generativelanguage.googleapis.com/v1beta/openai
  - OpenRouter:        https://openrouter.ai/api/v1
  - DeepSeek:          https://api.deepseek.com/v1
  - OpenAI:            https://api.openai.com/v1
  - Kimi / Qwen / etc.

The API key is ALWAYS read from an environment variable (name configured
via `api_key_env`), NEVER from the config file itself. This keeps keys
out of git and out of AI chat logs.

Usage:
    python3 ai_remix.py <config.json> <candidates.json> > input.json

Exit codes:
    0 = success
    1 = validation or API error
    2 = bad input arguments
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompt_template(repo_root: Path) -> str:
    """Load the remix instructions from prompts/remix-instructions.md."""
    p = repo_root / "prompts" / "remix-instructions.md"
    if not p.exists():
        raise SystemExit(
            f"Prompt template not found: {p}\n"
            f"The prompts/ directory should ship with the repo."
        )
    return p.read_text(encoding="utf-8")


def build_prompt(template: str, candidates: dict) -> str:
    """Fill the template's placeholders with the candidates JSON."""
    date = candidates.get("date", "")
    candidates_json = json.dumps(candidates, ensure_ascii=False, indent=2)
    return (
        template
        .replace("{{DATE}}", date)
        .replace("{{CANDIDATES_JSON}}", candidates_json)
    )


# ---------------------------------------------------------------------------
# LLM call (OpenAI-compatible)
# ---------------------------------------------------------------------------

def call_llm(config: dict, prompt: str) -> str:
    """Call an OpenAI-compatible /chat/completions endpoint.

    Works with any provider that implements the OpenAI chat API shape:
    Gemini (openai-compat layer), OpenRouter, DeepSeek, OpenAI, Kimi, etc.
    """
    ai_config = config["ai"]
    base_url = ai_config["base_url"].rstrip("/")
    model = ai_config["model"]
    key_env = ai_config.get("api_key_env", "OPENAI_API_KEY")
    temperature = float(ai_config.get("temperature", 0.3))
    provider = ai_config.get("provider", "unknown")

    api_key = os.environ.get(key_env, "").strip()
    if not api_key:
        raise SystemExit(
            f"Missing API key. Set the environment variable: {key_env}\n\n"
            f"Examples:\n"
            f"  Gemini:     export GEMINI_API_KEY=xxx\n"
            f"  OpenRouter: export OPENROUTER_API_KEY=xxx\n"
            f"  DeepSeek:   export DEEPSEEK_API_KEY=xxx\n"
            f"  OpenAI:     export OPENAI_API_KEY=xxx\n\n"
            f"Get a Gemini key for free: https://aistudio.google.com/apikey"
        )

    url = f"{base_url}/chat/completions"
    body: dict = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }

    # JSON mode: most providers support it, but Gemini's openai-compat layer
    # is picky. Make it opt-out via config so we can disable if it causes 400s.
    if ai_config.get("response_format_json", True):
        body["response_format"] = {"type": "json_object"}

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    print(
        f"→ Calling {provider} ({model}) at {base_url} ...",
        file=sys.stderr,
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            pass
        hint = ""
        if e.code == 401:
            hint = f"\nHint: check that ${key_env} is exported and valid"
        elif e.code == 429:
            hint = "\nHint: rate limited — try a different model or wait"
        elif e.code == 400 and "response_format" in err_body:
            hint = (
                "\nHint: this provider may not support response_format=json_object.\n"
                "       Set ai.response_format_json = false in config.json"
            )
        raise SystemExit(
            f"HTTP {e.code} from LLM API: {e.reason}{hint}\n"
            f"Response: {err_body[:500]}"
        )
    except urllib.error.URLError as e:
        raise SystemExit(
            f"Network error calling LLM: {e.reason}\n"
            f"Hint: check your internet / proxy settings"
        )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"LLM returned non-JSON: {raw[:500]}")

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise SystemExit(f"Unexpected LLM response shape: {raw[:500]}")

    return content


# ---------------------------------------------------------------------------
# Output parsing and validation
# ---------------------------------------------------------------------------

def strip_code_fences(s: str) -> str:
    """Some models wrap JSON in ```json ... ``` even with response_format=json.

    We strip fences defensively.
    """
    s = s.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines)
    return s.strip()


def validate_input(data: dict) -> None:
    """Mirror build_card.py's validator so we catch errors BEFORE the card step.

    Keeps error messages close to the LLM call — makes debugging easier.
    """
    if "date" not in data:
        raise ValueError("Output missing 'date'")
    if "sections" not in data:
        raise ValueError("Output missing 'sections'")

    s = data["sections"]
    required = {"top3": 3, "policy": 3, "hubei": 2, "ai_power": 2}
    for key, expected in required.items():
        if key not in s:
            raise ValueError(f"Missing section '{key}'")
        if not isinstance(s[key], list):
            raise ValueError(f"Section '{key}' must be a list")
        if len(s[key]) != expected:
            raise ValueError(
                f"Section '{key}' has {len(s[key])} items, expected {expected}"
            )
        for i, item in enumerate(s[key]):
            for field in ("title", "url"):
                if not item.get(field):
                    raise ValueError(
                        f"Section '{key}' item {i} missing or empty '{field}'"
                    )
            # Fill missing summary/impact with placeholder instead of failing
            if not item.get("summary"):
                item["summary"] = ""
            if not item.get("impact"):
                item["impact"] = ""
            if not item["url"].startswith(("http://", "https://")):
                raise ValueError(
                    f"Section '{key}' item {i} has invalid URL: {item['url'][:60]!r}"
                )

    if "copper" not in s:
        raise ValueError("Missing 'copper' in sections")
    for field in ("mean_price", "change", "price_range", "brand", "date", "judgment"):
        if not s["copper"].get(field):
            raise ValueError(f"Copper block missing or empty '{field}'")

    if "opportunities" not in s:
        raise ValueError("Missing 'opportunities'")
    if not isinstance(s["opportunities"], list) or len(s["opportunities"]) < 3:
        raise ValueError("Opportunities must be a list of at least 3 strings")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: python3 ai_remix.py <config.json> <candidates.json> > input.json",
            file=sys.stderr,
        )
        return 2

    config_path = Path(sys.argv[1])
    candidates_path = Path(sys.argv[2])

    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 2
    if not candidates_path.exists():
        print(f"Candidates file not found: {candidates_path}", file=sys.stderr)
        return 2

    config = json.loads(config_path.read_text(encoding="utf-8"))
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))

    # prompts/remix-instructions.md lives at repo root (parent of scripts/)
    repo_root = Path(__file__).resolve().parent.parent
    template = load_prompt_template(repo_root)
    prompt = build_prompt(template, candidates)

    raw_output = call_llm(config, prompt)
    cleaned = strip_code_fences(raw_output)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"LLM output is not valid JSON: {e}", file=sys.stderr)
        print("--- raw output (first 2000 chars) ---", file=sys.stderr)
        print(cleaned[:2000], file=sys.stderr)
        return 1

    try:
        validate_input(data)
    except ValueError as e:
        print(f"LLM output failed validation: {e}", file=sys.stderr)
        print("--- output (first 2000 chars) ---", file=sys.stderr)
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000], file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    print(
        "✓ Remix done: 10 news items + copper + opportunities",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
