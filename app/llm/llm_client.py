from __future__ import annotations

from typing import Protocol

from app.core.config import get_settings


class BaseLLMClient(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.base_url = base_url if base_url is not None else settings.openai_base_url
        self.model_name = model_name or settings.llm_model_name
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for OpenAI-compatible LLM generation. "
                "Week 3 does not default to this provider."
            )

    def generate(self, prompt: str) -> str:
        raise NotImplementedError(
            "OpenAI-compatible LLM calls are a Week 3 optional interface stub."
        )


def get_llm_client(provider: str | None = None) -> BaseLLMClient:
    settings = get_settings()
    selected_provider = (provider or settings.llm_provider).lower().replace("-", "_")
    if selected_provider == "mock":
        from app.llm.mock_llm import MockLLMClient

        return MockLLMClient()
    if selected_provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleLLMClient()
    raise ValueError(f"Unsupported LLM provider: {selected_provider}")
