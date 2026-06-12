# ruff: noqa: E402
"""Forced real-LLM smoke test.

Runs a single minimal-token call against the configured real provider (DeepSeek)
and prints provenance. It never prints the API key and fails loudly if the
provider is mock or the key is missing.

Usage:
    python -m uv run python scripts/smoke_real_llm.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.llm.llm_client import LLMClientError, get_llm_client

_MINIMAL_PROMPT = (
    "Return exactly this JSON object and nothing else: "
    '{"ok": true, "provider": "deepseek"}'
)


def _api_key_present(settings) -> bool:
    if settings.llm_provider.lower() == "deepseek":
        return bool(settings.deepseek_api_key)
    return bool(settings.openai_api_key)


def main() -> int:
    settings = get_settings()
    provider = settings.llm_provider.lower()

    if provider == "mock":
        print("real_llm_call_succeeded: false")
        print("error: LLM_PROVIDER=mock; the smoke test requires a real provider.")
        return 1
    if not _api_key_present(settings):
        print("real_llm_call_succeeded: false")
        print(f"error: missing API key for LLM_PROVIDER={settings.llm_provider}.")
        return 1

    client = get_llm_client(settings.llm_provider, max_output_tokens=64, purpose="answer")
    print(f"provider: {settings.llm_provider}")
    print(f"model: {settings.llm_model_name}")
    print(f"base_url_host: {getattr(client, 'base_url_host', 'n/a')}")
    print(f"is_mock_llm: {getattr(client, 'provider', '') == 'mock'}")

    try:
        raw = client.generate(_MINIMAL_PROMPT)
    except LLMClientError as exc:
        # Error messages from the client never contain the key.
        print("real_llm_call_succeeded: false")
        print(f"error: {exc}")
        return 1

    preview = " ".join(raw.split())[:200]
    parsed_ok = True
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        parsed_ok = False

    usage = getattr(client, "last_usage", None)
    print(f"response_text_preview: {preview}")
    print(f"parsed_json_ok: {parsed_ok}")
    print(f"call_count: {getattr(client, 'call_count', 0)}")
    if usage:
        print("usage_returned: true")
        print(f"usage_prompt_tokens: {usage.get('prompt_tokens')}")
        print(f"usage_completion_tokens: {usage.get('completion_tokens')}")
        print(f"usage_total_tokens: {usage.get('total_tokens')}")
    else:
        print("usage_returned: false")
    print("real_llm_call_succeeded: true")
    print(f"is_mock_llm: {getattr(client, 'provider', '') == 'mock'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
