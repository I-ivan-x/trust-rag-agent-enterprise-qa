from __future__ import annotations

import pytest

from app.eval.q5_provenance import (
    Q5ModelIdentity,
    canonical_q5_model_family,
    q5_hash_payload,
    q5_model_deployment_fingerprint,
    validate_q5_cross_family_identities,
)


def test_q5_openai_provider_aliases_share_family_and_deployment() -> None:
    openai = _trusted_identity(
        provider="openai",
        instance_type="app.llm.llm_client.OpenAICompatibleLLMClient",
        host="gateway.example.test",
        model="shared-model",
    )
    compatible = _trusted_identity(
        provider="openai_compatible",
        instance_type="app.llm.llm_client.OpenAICompatibleLLMClient",
        host="gateway.example.test",
        model="shared-model",
    )

    assert canonical_q5_model_family(openai) == "openai_compatible"
    assert canonical_q5_model_family(compatible) == "openai_compatible"
    assert q5_model_deployment_fingerprint(openai) == (
        q5_model_deployment_fingerprint(compatible)
    )
    with pytest.raises(ValueError, match="same model deployment"):
        validate_q5_cross_family_identities([openai], [compatible])


def test_q5_deepseek_and_xiaomi_are_distinct_canonical_families() -> None:
    deepseek = _trusted_identity(
        provider="deepseek",
        instance_type="app.llm.llm_client.DeepSeekLLMClient",
        host="api.deepseek.com",
        model="deepseek-chat",
    )
    xiaomi = _trusted_identity(
        provider="xiaomi",
        instance_type="app.llm.llm_client.XiaomiLLMClient",
        host="api.xiaomimimo.com",
        model="mimo-v2",
    )

    assert canonical_q5_model_family(deepseek) == "deepseek"
    assert canonical_q5_model_family(xiaomi) == "xiaomi"
    validate_q5_cross_family_identities([deepseek], [xiaomi])


def _trusted_identity(
    *,
    provider: str,
    instance_type: str,
    host: str,
    model: str,
) -> Q5ModelIdentity:
    payload = {
        "provider": provider,
        "model_name": model,
        "instance_type": instance_type,
        "identity_kind": "trusted_real_client",
        "mock_instance": False,
        "trusted_real_client": True,
        "base_url_host": host,
    }
    return Q5ModelIdentity(
        **payload,
        identity_sha256=q5_hash_payload(payload),
    )
