from __future__ import annotations

import pytest

from app.core.config import Settings
from app.eval.judge.guard import JudgeConfigurationError, assert_secondary_judge_family


def test_secondary_judge_guard_rejects_same_model_family() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="deepseek",
        llm_model_name="deepseek-chat",
        judge_llm_provider="deepseek",
        judge_llm_model_name="deepseek-reasoner",
    )

    with pytest.raises(JudgeConfigurationError):
        assert_secondary_judge_family(settings)


def test_secondary_judge_guard_allows_xiaomi_for_deepseek_system() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="deepseek",
        llm_model_name="deepseek-chat",
        judge_llm_provider="xiaomi",
        judge_llm_model_name="mimo-v2.5-pro",
    )

    assert_secondary_judge_family(settings)
