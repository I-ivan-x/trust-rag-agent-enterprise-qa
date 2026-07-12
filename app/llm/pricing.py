"""Deterministic LLM cost telemetry derived from provider usage and sealed prices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEEPSEEK_PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"
DEEPSEEK_PRICING_AS_OF = "2026-07-12"


@dataclass(frozen=True)
class LLMTokenPrices:
    input_cache_hit_per_million_usd: float
    input_cache_miss_per_million_usd: float
    output_per_million_usd: float
    source: str
    as_of: str


@dataclass(frozen=True)
class LLMCostTelemetry:
    billed_cost_usd: float | None
    estimated_cost_usd: float | None
    all_cache_miss_cost_upper_usd: float | None
    pricing_source: str | None
    pricing_as_of: str | None


_DEEPSEEK_FLASH = LLMTokenPrices(
    input_cache_hit_per_million_usd=0.0028,
    input_cache_miss_per_million_usd=0.14,
    output_per_million_usd=0.28,
    source=DEEPSEEK_PRICING_SOURCE,
    as_of=DEEPSEEK_PRICING_AS_OF,
)
_DEEPSEEK_PRO = LLMTokenPrices(
    input_cache_hit_per_million_usd=0.003625,
    input_cache_miss_per_million_usd=0.435,
    output_per_million_usd=0.87,
    source=DEEPSEEK_PRICING_SOURCE,
    as_of=DEEPSEEK_PRICING_AS_OF,
)


def llm_cost_telemetry(
    *,
    provider: str | None,
    model_name: str | None,
    usage: dict[str, Any],
) -> LLMCostTelemetry:
    """Return billed cost separately from a reproducible cache-aware estimate."""

    billed = _optional_nonnegative_number(
        usage.get("cost_usd", usage.get("total_cost_usd"))
    )
    prices = _prices_for(provider=provider, model_name=model_name)
    if prices is None:
        return LLMCostTelemetry(
            billed_cost_usd=billed,
            estimated_cost_usd=None,
            all_cache_miss_cost_upper_usd=None,
            pricing_source=None,
            pricing_as_of=None,
        )

    prompt_tokens = _nonnegative_int(usage.get("prompt_tokens"))
    completion_tokens = _nonnegative_int(usage.get("completion_tokens"))
    cache_hit_tokens = _cache_hit_tokens(usage, prompt_tokens=prompt_tokens)
    explicit_miss = _optional_nonnegative_int(usage.get("prompt_cache_miss_tokens"))
    cache_miss_tokens = (
        max(explicit_miss, prompt_tokens - cache_hit_tokens)
        if explicit_miss is not None
        else max(0, prompt_tokens - cache_hit_tokens)
    )
    if cache_hit_tokens + cache_miss_tokens > prompt_tokens:
        cache_miss_tokens = max(0, prompt_tokens - cache_hit_tokens)

    estimated = (
        cache_hit_tokens * prices.input_cache_hit_per_million_usd
        + cache_miss_tokens * prices.input_cache_miss_per_million_usd
        + completion_tokens * prices.output_per_million_usd
    ) / 1_000_000
    upper = (
        prompt_tokens * prices.input_cache_miss_per_million_usd
        + completion_tokens * prices.output_per_million_usd
    ) / 1_000_000
    return LLMCostTelemetry(
        billed_cost_usd=billed,
        estimated_cost_usd=round(estimated, 12),
        all_cache_miss_cost_upper_usd=round(upper, 12),
        pricing_source=prices.source,
        pricing_as_of=prices.as_of,
    )


def _prices_for(
    *,
    provider: str | None,
    model_name: str | None,
) -> LLMTokenPrices | None:
    provider_value = str(provider or "").lower().replace("-", "_")
    model_value = str(model_name or "").lower().replace("_", "-")
    is_deepseek = provider_value == "deepseek" or model_value.startswith("deepseek-")
    if not is_deepseek:
        return None
    if model_value in {
        "deepseek-chat",
        "deepseek-reasoner",
        "deepseek-v4-flash",
    }:
        return _DEEPSEEK_FLASH
    if model_value == "deepseek-v4-pro":
        return _DEEPSEEK_PRO
    return None


def _cache_hit_tokens(usage: dict[str, Any], *, prompt_tokens: int) -> int:
    direct = _optional_nonnegative_int(usage.get("prompt_cache_hit_tokens"))
    if direct is not None:
        return min(prompt_tokens, direct)
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        nested = _optional_nonnegative_int(details.get("cached_tokens"))
        if nested is not None:
            return min(prompt_tokens, nested)
    return 0


def _nonnegative_int(value: Any) -> int:
    parsed = _optional_nonnegative_int(value)
    return parsed if parsed is not None else 0


def _optional_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


def _optional_nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)
