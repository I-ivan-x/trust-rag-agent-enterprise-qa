from __future__ import annotations

from copy import deepcopy

import pytest

from app.eval.q5_metrics import (
    Q5_BOOTSTRAP_MIN_RESAMPLES,
    Q5_ESCALATE_EVERYTHING_CONTROL,
    Q5_HYBRID_SYSTEM,
    Q5_LLM_SYSTEM,
    Q5_RULE_SYSTEM,
    compute_q5_metrics,
    evaluate_q5_gates,
    paired_bootstrap_q5,
)


def _graded_row(
    case_id: str,
    system: str,
    *,
    success: bool,
    stratum: str = "semantic",
    run_index: int = 1,
    authorized: bool = True,
) -> dict:
    return {
        "case_id": case_id,
        "system": system,
        "run_index": run_index,
        "stratum": stratum,
        "task_success": success,
        "trajectory_qualified_success": success,
        "fallback_assisted_success": False,
        "terminal_action_correct": success,
        "required_observation_count": 1,
        "observed_required_count": int(success),
        "transition_valid": True,
        "final_action": "open_remediation_ticket" if success else "escalate_to_human",
        "correct_escalation": False,
        "authorized": authorized,
        "committed_side_effect": False,
        "unauthorized_action_blocked": not authorized,
        "F11": False,
        "F12": not success,
        "F13": False,
        "F14": False,
        "F15": not success,
        "F16": False,
        "F17": False,
        "restricted_text_exposure_count": 0,
        "unsafe_tool_call_count": 0,
        "tool_schema_invalid_count": 0,
        "premature_terminal_count": 0,
        "approval_bypass": False,
        "llm_calls": 1 if system != Q5_RULE_SYSTEM else 0,
        "prompt_tokens": 10 if system != Q5_RULE_SYSTEM else 0,
        "completion_tokens": 2 if system != Q5_RULE_SYSTEM else 0,
        "total_tokens": 12 if system != Q5_RULE_SYSTEM else 0,
        "cost_usd": 0.0,
        "estimated_cost_usd": 0.0,
        "all_cache_miss_cost_upper_usd": 0.0,
        "latency_ms": 1.0,
        "observation_count": 1,
        "route": "llm" if system != Q5_RULE_SYSTEM else "rule",
        "trajectory_sha256": f"trajectory-{case_id}-{system}",
    }


def test_q5_paired_bootstrap_is_case_paired_and_seed_reproducible() -> None:
    rows = [
        _graded_row("case-a", Q5_RULE_SYSTEM, success=False),
        _graded_row("case-a", Q5_HYBRID_SYSTEM, success=True),
        _graded_row("case-b", Q5_RULE_SYSTEM, success=False),
        _graded_row("case-b", Q5_HYBRID_SYSTEM, success=True),
    ]
    first = paired_bootstrap_q5(
        rows,
        treatment_system=Q5_HYBRID_SYSTEM,
        control_system=Q5_RULE_SYSTEM,
        stratum="semantic",
        seed=17,
        resamples=Q5_BOOTSTRAP_MIN_RESAMPLES,
    )
    second = paired_bootstrap_q5(
        list(reversed(rows)),
        treatment_system=Q5_HYBRID_SYSTEM,
        control_system=Q5_RULE_SYSTEM,
        stratum="semantic",
        seed=17,
        resamples=Q5_BOOTSTRAP_MIN_RESAMPLES,
    )

    assert first == second
    assert first["paired_case_count"] == 2
    assert first["observed_delta"] == 1.0
    assert first["ci_lower"] == first["ci_upper"] == 1.0

    with pytest.raises(ValueError, match="at least 10000"):
        paired_bootstrap_q5(
            rows,
            treatment_system=Q5_HYBRID_SYSTEM,
            control_system=Q5_RULE_SYSTEM,
            seed=17,
            resamples=9_999,
        )

    with pytest.raises(ValueError, match="complete case pairing"):
        paired_bootstrap_q5(
            rows[:-1],
            treatment_system=Q5_HYBRID_SYSTEM,
            control_system=Q5_RULE_SYSTEM,
            seed=17,
            resamples=Q5_BOOTSTRAP_MIN_RESAMPLES,
        )

    incomplete_runs = [
        _graded_row("case-a", Q5_RULE_SYSTEM, success=False, run_index=1),
        _graded_row("case-a", Q5_RULE_SYSTEM, success=False, run_index=2),
        _graded_row("case-a", Q5_HYBRID_SYSTEM, success=True, run_index=1),
    ]
    with pytest.raises(ValueError, match="complete run-index pairing"):
        paired_bootstrap_q5(
            incomplete_runs,
            treatment_system=Q5_HYBRID_SYSTEM,
            control_system=Q5_RULE_SYSTEM,
            seed=17,
            resamples=Q5_BOOTSTRAP_MIN_RESAMPLES,
        )


def test_q5_metrics_cover_outcome_safety_efficiency_and_consistency() -> None:
    rows = [
        _graded_row("case-a", Q5_RULE_SYSTEM, success=False, authorized=False),
        _graded_row("case-a", Q5_LLM_SYSTEM, success=True, authorized=False),
        _graded_row("case-a", Q5_HYBRID_SYSTEM, success=True, authorized=False),
        _graded_row(
            "case-b",
            Q5_RULE_SYSTEM,
            success=True,
            stratum="deterministic",
        ),
        _graded_row(
            "case-b",
            Q5_LLM_SYSTEM,
            success=True,
            stratum="deterministic",
        ),
        _graded_row(
            "case-b",
            Q5_HYBRID_SYSTEM,
            success=True,
            stratum="deterministic",
        ),
    ]
    metrics = compute_q5_metrics(
        rows,
        k=1,
        seed=23,
        bootstrap_resamples=Q5_BOOTSTRAP_MIN_RESAMPLES,
    )

    hybrid = metrics["by_system"][Q5_HYBRID_SYSTEM]
    assert hybrid["task_success"] == 1.0
    assert hybrid["trajectory_qualified_success"] == 1.0
    assert hybrid["task_success_by_stratum"] == {
        "deterministic": 1.0,
        "semantic": 1.0,
    }
    assert hybrid["terminal_action_correct"] == 1.0
    assert hybrid["required_observation_recall"] == 1.0
    assert hybrid["unauthorized_action_blocked"] == 1.0
    assert hybrid["F11"] == hybrid["F13"] == hybrid["F17"] == 0
    assert hybrid["pass_1"] == 1.0
    assert hybrid["trajectory_consistency"] == 1.0
    assert metrics["comparisons"]["semantic_uplift_hybrid_vs_rule"] == 1.0
    assert (
        metrics["comparisons"]["semantic_uplift_metric"]
        == "trajectory_qualified_success"
    )


def test_q5_g1_semantic_uplift_requires_trajectory_qualified_success() -> None:
    rows = [
        _graded_row("case-a", Q5_RULE_SYSTEM, success=False),
        _graded_row("case-a", Q5_HYBRID_SYSTEM, success=True),
    ]
    rows[1]["trajectory_qualified_success"] = False

    metrics = compute_q5_metrics(
        rows,
        k=1,
        seed=31,
        bootstrap_resamples=Q5_BOOTSTRAP_MIN_RESAMPLES,
    )

    assert metrics["by_system"][Q5_HYBRID_SYSTEM]["task_success"] == 1.0
    assert (
        metrics["by_system"][Q5_HYBRID_SYSTEM][
            "trajectory_qualified_success"
        ]
        == 0.0
    )
    assert metrics["comparisons"]["semantic_uplift_hybrid_vs_rule"] == 0.0
    assert metrics["comparisons"]["paired_bootstrap_ci"]["metric"] == (
        "trajectory_qualified_success"
    )
    assert metrics["comparisons"]["paired_bootstrap_ci"]["resamples"] == 10_000


def test_q5_diagnostic_protocol_metrics_are_aggregated_separately() -> None:
    row = _graded_row("case-a", Q5_HYBRID_SYSTEM, success=True)
    row.update(
        {
            "fallback_assisted_success": True,
            "tool_schema_invalid_count": 2,
            "premature_terminal_count": 1,
        }
    )

    metrics = compute_q5_metrics(
        [
            _graded_row("case-a", Q5_RULE_SYSTEM, success=False),
            row,
        ],
        k=1,
        seed=37,
        bootstrap_resamples=Q5_BOOTSTRAP_MIN_RESAMPLES,
    )["by_system"][Q5_HYBRID_SYSTEM]

    assert metrics["fallback_assisted_success"] == 1.0
    assert metrics["tool_schema_invalid_count"] == 2
    assert metrics["premature_terminal_count"] == 1


def test_q5_metrics_report_every_f11_through_f17_failure() -> None:
    rows = []
    for system in (Q5_RULE_SYSTEM, Q5_LLM_SYSTEM, Q5_HYBRID_SYSTEM):
        row = _graded_row("failure-case", system, success=False)
        for code in range(11, 18):
            row[f"F{code}"] = True
        row["restricted_text_exposure_count"] = 1
        row["unsafe_tool_call_count"] = 1
        rows.append(row)
    metrics = compute_q5_metrics(
        rows,
        k=1,
        seed=29,
        bootstrap_resamples=Q5_BOOTSTRAP_MIN_RESAMPLES,
    )["by_system"][Q5_HYBRID_SYSTEM]

    assert {metrics[f"F{code}"] for code in range(11, 18)} == {1}
    assert metrics["restricted_text_exposure_count"] == 1
    assert metrics["unsafe_tool_call_count"] == 1


def _safe_metrics(
    *,
    task_success: float,
    semantic: float,
    deterministic: float,
    calls: int,
    tokens: int,
) -> dict:
    return {
        "task_success": task_success,
        "task_success_by_stratum": {
            "semantic": semantic,
            "deterministic": deterministic,
        },
        "F11": 0,
        "F13": 0,
        "F17": 0,
        "restricted_text_exposure_count": 0,
        "unsafe_tool_call_count": 0,
        "unauthorized_action_blocked": 1.0,
        "llm_calls": calls,
        "total_tokens": tokens,
        "anti_gaming_ok": True,
        "anti_gaming_failure": False,
    }


def _headline_summary() -> dict:
    primary = {
        Q5_RULE_SYSTEM: _safe_metrics(
            task_success=0.65,
            semantic=0.50,
            deterministic=1.0,
            calls=0,
            tokens=0,
        ),
        Q5_LLM_SYSTEM: _safe_metrics(
            task_success=0.80,
            semantic=0.75,
            deterministic=1.0,
            calls=100,
            tokens=1_000,
        ),
        Q5_HYBRID_SYSTEM: _safe_metrics(
            task_success=0.79,
            semantic=0.70,
            deterministic=1.0,
            calls=50,
            tokens=600,
        ),
    }
    confirmatory = {
        Q5_RULE_SYSTEM: _safe_metrics(
            task_success=0.60,
            semantic=0.50,
            deterministic=0.0,
            calls=0,
            tokens=0,
        ),
        Q5_HYBRID_SYSTEM: _safe_metrics(
            task_success=0.70,
            semantic=0.60,
            deterministic=0.0,
            calls=10,
            tokens=100,
        ),
    }
    return {
        "run_metadata": {
            "mode": "real",
            "mock_used": False,
            "real_run": True,
            "dataset_partition": "test",
            "verified_run_ledger": [
                {"verified": True, "model_role": "primary", "run_id": "p"},
                {
                    "verified": True,
                    "model_role": "confirmatory",
                    "run_id": "c",
                },
            ],
        },
        "analytic_controls": {
            Q5_ESCALATE_EVERYTHING_CONTROL: {
                "anti_gaming_ok": False,
                "anti_gaming_failure": True,
                "task_success": 0.2,
                "escalation_rate": 1.0,
                "over_escalation_rate": 0.8,
            }
        },
        "by_model_role": {
            "primary": {
                "by_system": primary,
                "comparisons": {
                    "semantic_uplift_hybrid_vs_rule": 0.20,
                    "semantic_uplift_metric": "trajectory_qualified_success",
                    "paired_bootstrap_ci": {
                        "metric": "trajectory_qualified_success",
                        "ci_lower": 0.01,
                        "ci_upper": 0.30,
                    },
                },
            },
            "confirmatory": {
                "by_system": confirmatory,
                "comparisons": {},
            },
        },
    }


@pytest.mark.parametrize("mode", ["mock", "dev"])
def test_q5_mock_and_dev_runs_are_never_headline(mode: str) -> None:
    summary = _headline_summary()
    summary["run_metadata"].update(
        {"mode": mode, "mock_used": mode == "mock", "real_run": False}
    )
    gates = evaluate_q5_gates(summary)

    assert all(item["passed"] for item in gates["gates"].values())
    assert gates["q5_headline_eligible"] is False
    assert "mock_dev_or_non_test_run" in gates["headline_blockers"]


def test_q5_g1_rejects_task_success_bootstrap_label() -> None:
    summary = _headline_summary()
    comparisons = summary["by_model_role"]["primary"]["comparisons"]
    comparisons["semantic_uplift_metric"] = "task_success"
    comparisons["paired_bootstrap_ci"]["metric"] = "task_success"

    gates = evaluate_q5_gates(summary)

    assert gates["gates"]["G1_llm_necessary_value"]["passed"] is False
    assert gates["q5_headline_eligible"] is False


def test_q5_f17_or_restricted_exposure_invalidates_entire_run() -> None:
    summary = _headline_summary()
    summary["by_model_role"]["primary"]["by_system"][Q5_HYBRID_SYSTEM][
        "restricted_text_exposure_count"
    ] = 1
    summary["by_model_role"]["primary"]["by_system"][Q5_HYBRID_SYSTEM]["F17"] = 1
    gates = evaluate_q5_gates(summary)

    assert gates["run_valid"] is False
    assert gates["q5_headline_eligible"] is False
    assert gates["claim_scope"] == "invalid_run"


def test_q5_primary_and_confirmatory_run_count_discipline_is_strict() -> None:
    summary = _headline_summary()
    assert evaluate_q5_gates(summary)["q5_headline_eligible"] is True

    summary["run_metadata"]["verified_run_ledger"].append(
        {"verified": True, "model_role": "primary", "run_id": "p2"}
    )
    gates = evaluate_q5_gates(summary)
    assert gates["run_count_discipline"] is False
    assert gates["q5_headline_eligible"] is False


def test_q5_run_counts_ignore_unverified_self_reported_settings() -> None:
    summary = _headline_summary()
    summary["run_metadata"]["test_run_count_by_model_role"] = {
        "primary": 99,
        "confirmatory": 0,
    }
    gates = evaluate_q5_gates(summary)

    assert gates["verified_run_count_by_model_role"] == {
        "primary": 1,
        "confirmatory": 1,
    }
    assert gates["run_count_discipline"] is True


def test_q5_escalate_everything_cheater_is_explicitly_headline_ineligible() -> None:
    summary = _headline_summary()
    cheater = _safe_metrics(
        task_success=0.20,
        semantic=0.20,
        deterministic=0.20,
        calls=0,
        tokens=0,
    )
    cheater.update(
        {
            "anti_gaming_ok": False,
            "anti_gaming_failure": True,
            "over_escalation_rate": 0.80,
            "escalation_rate": 1.0,
        }
    )
    summary["by_model_role"]["primary"]["by_system"][
        "q5_escalate_everything"
    ] = cheater
    gates = evaluate_q5_gates(summary)

    assert gates["gates"]["G5_anti_gaming"]["passed"] is True
    assert gates["system_headline_eligibility"]["q5_escalate_everything"] is False

    cheater_only = deepcopy(summary)
    cheater_only["by_model_role"]["primary"]["by_system"] = {
        "q5_escalate_everything": cheater
    }
    assert evaluate_q5_gates(cheater_only)["q5_headline_eligible"] is False


def test_q5_missing_analytic_control_fails_g5_and_is_reported() -> None:
    summary = _headline_summary()
    summary.pop("analytic_controls")
    gates = evaluate_q5_gates(summary)

    assert gates["gates"]["G5_anti_gaming"]["passed"] is False
    assert gates["analytic_control_present"] is False
    assert gates["analytic_control_failure_detected"] is False
    assert gates["q5_headline_eligible"] is False
