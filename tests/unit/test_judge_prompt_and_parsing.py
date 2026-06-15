from __future__ import annotations

from app.eval.judge.custom_judge import CustomCitationJudge, parse_custom_verdict


class _FakeLLM:
    def __init__(self, raw: str = "{}") -> None:
        self.raw = raw

    def generate(self, prompt: str) -> str:
        return self.raw


def test_custom_judge_prompt_excludes_forbidden_audit_fields() -> None:
    judge = CustomCitationJudge(_FakeLLM())
    prompt = judge.build_prompt(
        "claim text",
        ["cited text"],
    )

    assert "claim text" in prompt
    assert "cited text" in prompt
    for forbidden in [
        "human_primary",
        "supported_by_human",
        "gold_answer",
        "expected_behavior",
        "final_agentic",
        "system_name",
    ]:
        assert forbidden not in prompt


def test_custom_judge_parse_failure_falls_back_to_unsupported() -> None:
    verdict = parse_custom_verdict("not json")

    assert verdict.label == "unsupported"
    assert verdict.wrong_side is False
    assert "judge_parse_failed" in verdict.warnings


def test_custom_judge_parses_wrong_side_alias() -> None:
    verdict = parse_custom_verdict(
        '{"label": "weak", "wrong_side": true, "rationale": "similar but wrong"}'
    )

    assert verdict.label == "weak"
    assert verdict.wrong_side is True
