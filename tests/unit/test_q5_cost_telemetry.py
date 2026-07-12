from __future__ import annotations

from app.eval.q5_provenance import Q5ModelIdentity, q5_hash_payload
from app.eval.q5_runner import _AuditedPolicyModel
from app.llm.pricing import (
    DEEPSEEK_PRICING_AS_OF,
    DEEPSEEK_PRICING_SOURCE,
    llm_cost_telemetry,
)


class UsageOnlyDelegate:
    def __init__(self, usage: dict) -> None:
        self.usage = usage
        self.call_count = 0
        self.last_usage = None

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        self.last_usage = dict(self.usage)
        return '{"kind":"terminal"}'


def _deepseek_identity() -> Q5ModelIdentity:
    payload = {
        "provider": "deepseek",
        "model_name": "deepseek-v4-flash",
        "instance_type": "app.llm.llm_client.DeepSeekLLMClient",
        "identity_kind": "trusted_real_client",
        "mock_instance": False,
        "trusted_real_client": True,
        "base_url_host": "api.deepseek.com",
    }
    return Q5ModelIdentity(
        **payload,
        identity_sha256=q5_hash_payload(payload),
    )


def test_q5_deepseek_cost_estimate_is_cache_aware_and_has_upper_bound() -> None:
    telemetry = llm_cost_telemetry(
        provider="deepseek",
        model_name="deepseek-v4-flash",
        usage={
            "prompt_tokens": 1_000,
            "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 400},
        },
    )

    assert telemetry.billed_cost_usd is None
    assert telemetry.estimated_cost_usd == 0.00011312
    assert telemetry.all_cache_miss_cost_upper_usd == 0.000168
    assert telemetry.pricing_source == DEEPSEEK_PRICING_SOURCE
    assert telemetry.pricing_as_of == DEEPSEEK_PRICING_AS_OF


def test_q5_real_usage_without_provider_bill_is_not_recorded_as_zero_cost() -> None:
    delegate = UsageOnlyDelegate(
        {
            "prompt_tokens": 1_000,
            "completion_tokens": 100,
            "total_tokens": 1_100,
        }
    )
    audited = _AuditedPolicyModel(
        delegate,
        restricted_markers=set(),
        model_identity=_deepseek_identity(),
    )

    audited.generate("Q5 protocol prompt")
    usage = audited.usage_snapshot()

    assert usage["cost_usd"] is None
    assert usage["billing_cost_status"] == "provider_not_reported"
    assert usage["estimated_cost_usd"] == 0.000168
    assert usage["all_cache_miss_cost_upper_usd"] == 0.000168
    assert usage["pricing_source"] == DEEPSEEK_PRICING_SOURCE
    assert usage["pricing_as_of"] == DEEPSEEK_PRICING_AS_OF


def test_q5_provider_billed_cost_remains_distinct_from_estimate() -> None:
    telemetry = llm_cost_telemetry(
        provider="deepseek",
        model_name="deepseek-chat",
        usage={
            "prompt_tokens": 1_000,
            "completion_tokens": 100,
            "cost_usd": 0.0002,
        },
    )

    assert telemetry.billed_cost_usd == 0.0002
    assert telemetry.estimated_cost_usd == 0.000168
    assert telemetry.all_cache_miss_cost_upper_usd == 0.000168
