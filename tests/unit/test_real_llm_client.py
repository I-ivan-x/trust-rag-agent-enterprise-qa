from __future__ import annotations

import json
import warnings

import httpx
import pytest

from app.llm.llm_client import (
    DeepSeekLLMClient,
    LLMClientError,
    OpenAICompatibleLLMClient,
    get_llm_client,
)


def _client(api_key: str = "unit-test-key") -> OpenAICompatibleLLMClient:
    return OpenAICompatibleLLMClient(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model_name="deepseek-v4-flash",
        provider="deepseek",
    )


def test_missing_api_key_fails_without_leaking() -> None:
    with pytest.raises(LLMClientError) as exc:
        OpenAICompatibleLLMClient(
            api_key="",
            base_url="https://api.deepseek.com",
            model_name="m",
            provider="deepseek",
        )
    assert "api key" in str(exc.value).lower()


def test_provider_metadata_excludes_key() -> None:
    client = _client(api_key="super-secret-123")
    metadata = client.provider_metadata()
    assert metadata["is_mock_llm"] is False
    assert metadata["llm_provider"] == "deepseek"
    assert metadata["base_url_host"] == "api.deepseek.com"
    assert "super-secret-123" not in json.dumps(metadata)


def test_generate_parses_openai_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": '{"answer_text":"ok"}'}}]}

    def fake_post(url, headers, json, timeout):  # noqa: A002 - mirror httpx signature
        captured["url"] = url
        captured["headers"] = headers
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    out = _client().generate("hello")
    assert out == '{"answer_text":"ok"}'
    assert str(captured["url"]).endswith("/v1/chat/completions")


def test_http_error_excludes_key(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
    response = httpx.Response(401, request=request)

    def fake_post(*args, **kwargs):
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(LLMClientError) as exc:
        _client(api_key="super-secret-123").generate("x")
    message = str(exc.value)
    assert "super-secret-123" not in message
    assert "401" in message


def test_deepseek_defaults_base_url() -> None:
    client = DeepSeekLLMClient(api_key="k", model_name="deepseek-v4-flash")
    assert client.base_url_host == "api.deepseek.com"
    assert client.provider == "deepseek"


def test_get_llm_client_mock_returns_mock() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        client = get_llm_client("mock")
    assert client.__class__.__name__ == "MockLLMClient"


def test_generate_records_calls_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm.usage import get_usage_tracker

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
            }

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())
    get_usage_tracker().reset()
    client = _client()
    client.generate("x")
    totals = get_usage_tracker().totals
    assert client.call_count == 1
    assert client.last_usage is not None and client.last_usage["total_tokens"] == 8
    assert totals.answer_calls == 1
    assert totals.total_tokens == 8
    assert totals.usage_reported is True


def test_smoke_script_fails_on_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    from app.core.config import Settings

    smoke = importlib.import_module("scripts.smoke_real_llm")
    monkeypatch.setattr(
        smoke, "get_settings", lambda: Settings(_env_file=None, llm_provider="mock")
    )
    assert smoke.main() == 1
