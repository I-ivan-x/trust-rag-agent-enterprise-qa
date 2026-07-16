from __future__ import annotations

import copy

import pytest

from app.eval.q5_claim_readiness import (
    evaluate_q5_claim_readiness,
    verify_q5_claim_readiness,
)


def test_q5_claim_readiness_empty_beneficial_evidence_never_passes() -> None:
    run, value, symbolic = _otherwise_passing_inputs()
    readiness = evaluate_q5_claim_readiness(run, value, symbolic)

    assert readiness["checks"]["semantic_headroom"] is True
    assert readiness["checks"]["within_policy_headroom"] is True
    assert readiness["checks"]["cross_policy_headroom"] is True
    assert readiness["checks"]["beneficial_value_capture"] is None
    assert readiness["valid"] is False
    assert readiness["blockers"] == ["beneficial_evidence_absent"]


@pytest.mark.parametrize("mutation", ["force_valid", "delete_blocker"])
def test_q5_claim_readiness_self_report_mutations_fail_closed(mutation: str) -> None:
    run, value, symbolic = _otherwise_passing_inputs()
    claimed = evaluate_q5_claim_readiness(run, value, symbolic)
    forged = copy.deepcopy(claimed)
    if mutation == "force_valid":
        forged["valid"] = True
    else:
        forged["blockers"] = []

    with pytest.raises(ValueError):
        verify_q5_claim_readiness(run, value, symbolic, forged)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("beneficial_value_capture", 1.0),
        ("beneficial_group_count", 1),
        ("beneficial_capture_numerator", 1),
        ("beneficial_capture_denominator", 1),
    ],
)
def test_q5_claim_readiness_rejects_inconsistent_beneficial_accounting(
    field: str,
    value: object,
) -> None:
    run, sidecar, symbolic = _otherwise_passing_inputs()
    sidecar[field] = value
    with pytest.raises(ValueError):
        evaluate_q5_claim_readiness(run, sidecar, symbolic)


def _otherwise_passing_inputs() -> tuple[dict, dict, dict]:
    run = {
        "by_system": {
            "q5_hybrid_agent": {
                "trajectory_qualified_success_by_stratum": {"semantic": 1.0},
                "within_policy_pair_success": 1.0,
                "cross_policy_pair_success": 1.0,
            }
        }
    }
    value = {
        "schema_version": "q5-value-summary-v2",
        "beneficial_group_count": 0,
        "beneficial_capture_numerator": 0,
        "beneficial_capture_denominator": 0,
        "beneficial_capture_vacuous": True,
        "beneficial_value_capture": None,
        "harmful_terminal_llm_exposure": 0,
        "hybrid_oracle_regret": 0.0,
        "hybrid_observation_planning_llm_calls_global": 3,
        "hybrid_observation_planning_llm_calls_semantic": 0,
        "hybrid_observation_planning_llm_calls_adversarial": 3,
        "hybrid_terminal_binding_llm_calls_global": 39,
        "hybrid_terminal_binding_llm_calls_semantic": 36,
        "hybrid_terminal_binding_llm_calls_adversarial": 3,
    }
    symbolic = {
        "schema_version": "q5-strong-symbolic-summary-v2",
        "semantic_success": 0.0,
        "within_policy_pair_success": 0.0,
        "cross_policy_pair_success": 0.0,
    }
    return run, value, symbolic
