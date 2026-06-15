from __future__ import annotations

from app.core.config import Settings, get_settings
from app.eval.judge.guard import assert_secondary_judge_family
from app.llm.llm_client import BaseLLMClient, OpenAICompatibleLLMClient, XiaomiLLMClient


def get_judge_llm_client(settings: Settings | None = None) -> BaseLLMClient:
    selected_settings = settings or get_settings()
    assert_secondary_judge_family(selected_settings)
    provider = selected_settings.judge_llm_provider.lower().replace("-", "_")
    if provider in {"xiaomi", "mimo"}:
        return XiaomiLLMClient(
            api_key=selected_settings.judge_api_key,
            base_url=selected_settings.judge_llm_base_url,
            model_name=selected_settings.judge_llm_model_name,
            timeout=selected_settings.judge_llm_timeout_seconds,
            max_output_tokens=selected_settings.judge_llm_max_output_tokens,
            temperature=selected_settings.judge_llm_temperature,
            purpose="judge",
        )
    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleLLMClient(
            api_key=selected_settings.judge_api_key,
            base_url=selected_settings.judge_llm_base_url,
            model_name=selected_settings.judge_llm_model_name,
            provider=provider,
            timeout=selected_settings.judge_llm_timeout_seconds,
            max_output_tokens=selected_settings.judge_llm_max_output_tokens,
            temperature=selected_settings.judge_llm_temperature,
            purpose="judge",
        )
    raise ValueError(f"Unsupported judge LLM provider: {provider}")
