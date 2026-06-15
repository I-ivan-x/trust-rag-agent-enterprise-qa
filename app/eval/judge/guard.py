from __future__ import annotations

from app.core.config import Settings


class JudgeConfigurationError(RuntimeError):
    """Raised when judge configuration violates model-family isolation."""


def model_family(provider: str | None, model_name: str | None) -> str:
    blob = f"{provider or ''} {model_name or ''}".lower().replace("-", "_")
    if "deepseek" in blob:
        return "deepseek"
    if "xiaomi" in blob or "mimo" in blob or "mime" in blob:
        return "xiaomi"
    if "gpt" in blob or "openai" in blob:
        return "openai"
    if "claude" in blob or "anthropic" in blob:
        return "anthropic"
    if "gemini" in blob or "google" in blob:
        return "google"
    if "qwen" in blob or "dashscope" in blob or "aliyun" in blob:
        return "qwen"
    normalized = blob.strip()
    return normalized or "unknown"


def assert_secondary_judge_family(settings: Settings) -> None:
    system_family = model_family(settings.llm_provider, settings.llm_model_name)
    judge_family = model_family(settings.judge_llm_provider, settings.judge_llm_model_name)
    if system_family == "mock" or judge_family == "unknown":
        return
    if system_family == judge_family:
        raise JudgeConfigurationError(
            "Judge model family must differ from the system LLM family to avoid "
            f"self-preference bias; both resolved to '{system_family}'."
        )
