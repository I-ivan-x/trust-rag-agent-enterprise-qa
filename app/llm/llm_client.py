from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.llm.usage import get_usage_tracker


class LLMClientError(RuntimeError):
    """Raised when a real LLM call fails. Never contains the API key."""


class BaseLLMClient(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class OpenAICompatibleLLMClient:
    """Real LLM client for any OpenAI-compatible /chat/completions endpoint.

    DeepSeek is reached through this client via its base_url. The API key is read
    from the environment, never logged, and never embedded in error messages.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        provider: str = "openai_compatible",
        timeout: float | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        purpose: str = "answer",
    ) -> None:
        settings = get_settings()
        self.provider = provider
        self.purpose = purpose
        self.call_count = 0
        self.last_usage: dict[str, Any] | None = None
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url or "").rstrip("/")
        self.model_name = model_name or settings.llm_model_name
        self.timeout = timeout if timeout is not None else settings.llm_timeout_seconds
        self.max_output_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else settings.llm_max_output_tokens
        )
        self.temperature = (
            temperature if temperature is not None else settings.llm_temperature
        )
        if not self.api_key:
            raise LLMClientError(
                f"Missing API key for LLM provider '{provider}'. Configure the provider "
                "key in the environment; no mock fallback is allowed for real runs."
            )
        if not self.base_url:
            raise LLMClientError(
                f"Missing base_url for LLM provider '{provider}'. Set LLM_BASE_URL."
            )

    @property
    def base_url_host(self) -> str:
        return urlsplit(self.base_url).netloc or self.base_url

    def _chat_completions_url(self) -> str:
        base = self.base_url
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/v1/chat/completions"

    def provider_metadata(self) -> dict[str, Any]:
        return {
            "llm_provider": self.provider,
            "llm_model_name": self.model_name,
            "is_mock_llm": False,
            "base_url_host": self.base_url_host,
        }

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are TrustRAG Enterprise QA. Respond with a single JSON "
                        "object only, no prose, no markdown fences."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        url = self._chat_completions_url()
        try:
            response = httpx.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise LLMClientError(
                f"LLM provider '{self.provider}' returned HTTP {exc.response.status_code} "
                f"from host {self.base_url_host}."
            ) from None
        except httpx.HTTPError as exc:
            raise LLMClientError(
                f"LLM provider '{self.provider}' request to host {self.base_url_host} "
                f"failed: {type(exc).__name__}."
            ) from None
        usage = data.get("usage") if isinstance(data, dict) else None
        self.last_usage = usage if isinstance(usage, dict) else None
        self.call_count += 1
        get_usage_tracker().record(self.purpose, self.last_usage)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError(
                f"LLM provider '{self.provider}' returned an unexpected response shape."
            ) from exc


class DeepSeekLLMClient(OpenAICompatibleLLMClient):
    """DeepSeek client. Reuses the OpenAI-compatible wire format via base_url."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout: float | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        purpose: str = "answer",
    ) -> None:
        settings = get_settings()
        super().__init__(
            api_key=api_key if api_key is not None else settings.deepseek_api_key,
            base_url=base_url or settings.llm_base_url or "https://api.deepseek.com",
            model_name=model_name or settings.llm_model_name,
            provider="deepseek",
            timeout=timeout,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            purpose=purpose,
        )


class XiaomiLLMClient(OpenAICompatibleLLMClient):
    """Xiaomi/MiMo OpenAI-compatible client used for secondary-family judging."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout: float | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        purpose: str = "judge",
    ) -> None:
        settings = get_settings()
        super().__init__(
            api_key=api_key if api_key is not None else settings.judge_api_key,
            base_url=base_url or settings.judge_llm_base_url,
            model_name=model_name or settings.judge_llm_model_name,
            provider="xiaomi",
            timeout=timeout if timeout is not None else settings.judge_llm_timeout_seconds,
            max_output_tokens=(
                max_output_tokens
                if max_output_tokens is not None
                else settings.judge_llm_max_output_tokens
            ),
            temperature=(
                temperature if temperature is not None else settings.judge_llm_temperature
            ),
            purpose=purpose,
        )


def get_llm_client(
    provider: str | None = None,
    *,
    model_name: str | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    purpose: str = "answer",
) -> BaseLLMClient:
    settings = get_settings()
    selected_provider = (provider or settings.llm_provider).lower().replace("-", "_")
    if selected_provider == "mock":
        from app.llm.mock_llm import MockLLMClient

        return MockLLMClient()
    if selected_provider == "deepseek":
        return DeepSeekLLMClient(
            model_name=model_name,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            purpose=purpose,
        )
    if selected_provider in {"xiaomi", "mimo"}:
        return XiaomiLLMClient(
            model_name=model_name,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            purpose=purpose,
        )
    if selected_provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleLLMClient(
            provider=selected_provider,
            model_name=model_name,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            purpose=purpose,
        )
    raise ValueError(f"Unsupported LLM provider: {selected_provider}")


def llm_provider_metadata(client: BaseLLMClient) -> dict[str, Any]:
    metadata = getattr(client, "provider_metadata", None)
    if callable(metadata):
        return metadata()
    return {"llm_provider": "mock", "is_mock_llm": True}


# Convenience for deterministic JSON parsing of raw model output downstream.
def safe_json_loads(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
