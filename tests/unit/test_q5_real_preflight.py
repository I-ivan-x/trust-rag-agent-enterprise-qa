from __future__ import annotations

import pytest

from app.llm.llm_client import get_llm_client
from scripts.preflight_q5_real import _budget, _real_command, build_parser


def test_q5_real_preflight_budget_caps_expected_and_hard_topology() -> None:
    expected = _budget(70, 512)
    hard = _budget(132, 512)

    assert expected == {
        "call_count": 70,
        "input_token_upper": 573_440,
        "output_token_upper": 35_840,
        "total_token_upper": 609_280,
        "cache_miss_cost_upper_usd": 0.090317,
    }
    assert hard == {
        "call_count": 132,
        "input_token_upper": 1_081_344,
        "output_token_upper": 67_584,
        "total_token_upper": 1_148_928,
        "cache_miss_cost_upper_usd": 0.170312,
    }


def test_q5_real_preflight_command_is_explicit_and_gold_free() -> None:
    args = build_parser().parse_args(
        [
            "--mock-run",
            "mock-run",
            "--output",
            "preflight.json",
            "--real-run-id",
            "q5-real-dev-primary",
        ]
    )

    command = _real_command(args)

    assert "--mode real" in command
    assert "--provider deepseek" in command
    assert "--model deepseek-v4-flash" in command
    assert "--temperature 0" in command
    assert "--max-output-tokens 512" in command
    assert "--timeout-seconds 30" in command
    assert "--thinking-mode disabled" in command
    assert "--k 1" in command
    assert "--gold" not in command
    assert "q5/test" not in command


def test_q5_non_deepseek_client_rejects_thinking_mode_before_construction() -> None:
    with pytest.raises(ValueError, match="only by the explicit DeepSeek client"):
        get_llm_client("xiaomi", thinking_mode="disabled")
