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

    assert canonical_q5_model_family(openai) == "unresolved"
    assert canonical_q5_model_family(compatible) == "unresolved"
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


def test_q5_native_and_proxied_deepseek_model_share_family() -> None:
    native = _trusted_identity(
        provider="deepseek",
        instance_type="app.llm.llm_client.DeepSeekLLMClient",
        host="api.deepseek.com",
        model="deepseek-chat",
    )
    proxy = _trusted_identity(
        provider="openai_compatible",
        instance_type="app.llm.llm_client.OpenAICompatibleLLMClient",
        host="proxy.example",
        model="deepseek-chat",
    )

    assert canonical_q5_model_family(native) == "deepseek"
    assert canonical_q5_model_family(proxy) == "deepseek"
    with pytest.raises(ValueError, match="distinct canonical model families"):
        validate_q5_cross_family_identities([native], [proxy])


def test_q5_native_xiaomi_and_proxied_mimo_model_share_family() -> None:
    native = _trusted_identity(
        provider="xiaomi",
        instance_type="app.llm.llm_client.XiaomiLLMClient",
        host="api.xiaomimimo.com",
        model="mimo-v2-flash",
    )
    proxy = _trusted_identity(
        provider="openai_compatible",
        instance_type="app.llm.llm_client.OpenAICompatibleLLMClient",
        host="proxy.example",
        model="mimo-v2-flash",
    )

    assert canonical_q5_model_family(native) == "xiaomi"
    assert canonical_q5_model_family(proxy) == "xiaomi"
    with pytest.raises(ValueError, match="distinct canonical model families"):
        validate_q5_cross_family_identities([native], [proxy])


def test_q5_conflicting_model_family_evidence_fails_closed() -> None:
    conflict = _trusted_identity(
        provider="deepseek",
        instance_type="app.llm.llm_client.DeepSeekLLMClient",
        host="api.deepseek.com",
        model="qwen2.5-72b-instruct",
    )

    with pytest.raises(ValueError, match="conflicting Q5 model-family evidence"):
        canonical_q5_model_family(conflict)


@pytest.mark.parametrize(
    ("model_name", "expected_family"),
    [("gpt-4.1-mini", "openai"), ("qwen2.5-72b-instruct", "qwen")],
)
def test_q5_proxy_model_name_identifies_family(
    model_name: str,
    expected_family: str,
) -> None:
    proxy = _trusted_identity(
        provider="openai_compatible",
        instance_type="app.llm.llm_client.OpenAICompatibleLLMClient",
        host="proxy.example",
        model=model_name,
    )

    assert canonical_q5_model_family(proxy) == expected_family


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
