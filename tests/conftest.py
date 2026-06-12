from __future__ import annotations

import pytest

from app.core import config

# The owner's local .env may point LLM_PROVIDER / REWRITE_LLM_PROVIDER at a real
# provider (e.g. deepseek) for headline runs. The deterministic test suite must not
# depend on that. This autouse fixture pins mock/rule-based providers for every test
# except those explicitly marked `realprovider` (the gated real-LLM smoke test),
# which is allowed to read the real .env configuration.
_MOCK_PROVIDER_ENV = {
    "LLM_PROVIDER": "mock",
    "LLM_MODEL_NAME": "mock-llm-v0",
    "REWRITE_LLM_PROVIDER": "rule_based",
    "REWRITE_LLM_MODEL_NAME": "mock-llm-v0",
}


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    if request.node.get_closest_marker("realprovider") is not None:
        yield
        return
    for key, value in _MOCK_PROVIDER_ENV.items():
        monkeypatch.setenv(key, value)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
