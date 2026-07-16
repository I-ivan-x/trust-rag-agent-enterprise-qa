"""Independent Q5 value-frontier claim-readiness evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

Q5_CLAIM_READINESS_SCHEMA = "q5-claim-readiness-v2"


def evaluate_q5_claim_readiness(
    run_summary: Mapping[str, Any],
    value_summary: Mapping[str, Any],
    symbolic_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare Hybrid evidence with the independently executed symbolic control."""

    if value_summary.get("schema_version") != "q5-value-summary-v2":
        raise ValueError("Q5 claim readiness v2 requires value sidecar v2")
    if symbolic_summary.get("schema_version") != "q5-strong-symbolic-summary-v2":
        raise ValueError("Q5 claim readiness v2 requires symbolic sidecar v2")

    hybrid = (run_summary.get("by_system") or {}).get("q5_hybrid_agent")
    if not isinstance(hybrid, Mapping):
        raise ValueError("Q5 claim readiness requires Hybrid run metrics")
    hybrid_semantic = _number(
        (hybrid.get("trajectory_qualified_success_by_stratum") or {}).get("semantic"),
        "Hybrid semantic success",
    )
    hybrid_within = _number(
        hybrid.get("within_policy_pair_success"),
        "Hybrid within-policy pair success",
    )
    hybrid_cross = _number(
        hybrid.get("cross_policy_pair_success"),
        "Hybrid cross-policy pair success",
    )
    symbolic_semantic = _number(
        symbolic_summary.get("semantic_success"),
        "symbolic semantic success",
    )
    symbolic_within = _number(
        symbolic_summary.get("within_policy_pair_success"),
        "symbolic within-policy pair success",
    )
    symbolic_cross = _number(
        symbolic_summary.get("cross_policy_pair_success"),
        "symbolic cross-policy pair success",
    )
    thresholds = {
        "semantic_margin": 0.1,
        "within_policy_margin": 0.166667,
        "cross_policy_margin": 0.166667,
        "beneficial_value_capture_min": 1.0,
        "harmful_terminal_llm_exposure_max": 0,
        "hybrid_oracle_regret_max": 0.027778,
        "hybrid_observation_planning_llm_calls_global": 3,
        "hybrid_observation_planning_llm_calls_semantic": 0,
        "hybrid_observation_planning_llm_calls_adversarial": 3,
        "hybrid_terminal_binding_llm_calls_global": 39,
        "hybrid_terminal_binding_llm_calls_semantic": 36,
        "hybrid_terminal_binding_llm_calls_adversarial": 3,
    }
    beneficial_count, beneficial_capture = _beneficial_evidence(value_summary)
    checks = {
        "semantic_headroom": hybrid_semantic >= symbolic_semantic + 0.1,
        "within_policy_headroom": hybrid_within >= symbolic_within + 0.166667,
        "cross_policy_headroom": hybrid_cross >= symbolic_cross + 0.166667,
        "beneficial_evidence_present": beneficial_count > 0,
        "beneficial_value_capture": (
            beneficial_capture >= 1.0 if beneficial_capture is not None else None
        ),
        "harmful_terminal_llm_exposure": value_summary.get(
            "harmful_terminal_llm_exposure"
        )
        == 0,
        "hybrid_oracle_regret": _number(
            value_summary.get("hybrid_oracle_regret"),
            "Hybrid oracle regret",
        )
        <= 0.027778,
        "hybrid_observation_planning_llm_calls_global": value_summary.get(
            "hybrid_observation_planning_llm_calls_global"
        )
        == 3,
        "hybrid_observation_planning_llm_calls_semantic": value_summary.get(
            "hybrid_observation_planning_llm_calls_semantic"
        )
        == 0,
        "hybrid_observation_planning_llm_calls_adversarial": value_summary.get(
            "hybrid_observation_planning_llm_calls_adversarial"
        )
        == 3,
        "hybrid_terminal_binding_llm_calls_global": value_summary.get(
            "hybrid_terminal_binding_llm_calls_global"
        )
        == 39,
        "hybrid_terminal_binding_llm_calls_semantic": value_summary.get(
            "hybrid_terminal_binding_llm_calls_semantic"
        )
        == 36,
        "hybrid_terminal_binding_llm_calls_adversarial": value_summary.get(
            "hybrid_terminal_binding_llm_calls_adversarial"
        )
        == 3,
    }
    impossible_headroom = any(
        (
            symbolic_semantic + 0.1 > 1.0,
            symbolic_within + 0.166667 > 1.0,
            symbolic_cross + 0.166667 > 1.0,
        )
    )
    blockers = []
    if impossible_headroom:
        blockers.append("claim_headroom")
    if beneficial_count == 0:
        blockers.append("beneficial_evidence_absent")
    blockers.extend(
        name
        for name, passed in checks.items()
        if passed is False and name != "beneficial_evidence_present"
    )
    return {
        "schema_version": Q5_CLAIM_READINESS_SCHEMA,
        "valid": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "checks": checks,
        "thresholds": thresholds,
        "observed": {
            "hybrid_semantic": hybrid_semantic,
            "symbolic_semantic": symbolic_semantic,
            "hybrid_within_policy": hybrid_within,
            "symbolic_within_policy": symbolic_within,
            "hybrid_cross_policy": hybrid_cross,
            "symbolic_cross_policy": symbolic_cross,
            "beneficial_group_count": beneficial_count,
            "beneficial_value_capture": beneficial_capture,
            "beneficial_capture_vacuous": value_summary[
                "beneficial_capture_vacuous"
            ],
            "harmful_terminal_llm_exposure": value_summary[
                "harmful_terminal_llm_exposure"
            ],
            "hybrid_oracle_regret": value_summary["hybrid_oracle_regret"],
            "hybrid_observation_planning_llm_calls_global": value_summary[
                "hybrid_observation_planning_llm_calls_global"
            ],
            "hybrid_observation_planning_llm_calls_semantic": value_summary[
                "hybrid_observation_planning_llm_calls_semantic"
            ],
            "hybrid_observation_planning_llm_calls_adversarial": value_summary[
                "hybrid_observation_planning_llm_calls_adversarial"
            ],
            "hybrid_terminal_binding_llm_calls_global": value_summary[
                "hybrid_terminal_binding_llm_calls_global"
            ],
            "hybrid_terminal_binding_llm_calls_semantic": value_summary[
                "hybrid_terminal_binding_llm_calls_semantic"
            ],
            "hybrid_terminal_binding_llm_calls_adversarial": value_summary[
                "hybrid_terminal_binding_llm_calls_adversarial"
            ],
        },
    }


def verify_q5_claim_readiness(
    run_summary: Mapping[str, Any],
    value_summary: Mapping[str, Any],
    symbolic_summary: Mapping[str, Any],
    claimed: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject deleted blockers or a self-reported validity rewrite."""

    expected = evaluate_q5_claim_readiness(
        run_summary,
        value_summary,
        symbolic_summary,
    )
    if dict(claimed) != expected:
        raise ValueError("Q5 claim-readiness receipt does not match recomputation")
    return expected


def _beneficial_evidence(value_summary: Mapping[str, Any]) -> tuple[int, float | None]:
    count = value_summary.get("beneficial_group_count")
    numerator = value_summary.get("beneficial_capture_numerator")
    denominator = value_summary.get("beneficial_capture_denominator")
    vacuous = value_summary.get("beneficial_capture_vacuous")
    capture = value_summary.get("beneficial_value_capture")
    if (
        type(count) is not int
        or type(numerator) is not int
        or type(denominator) is not int
        or type(vacuous) is not bool
        or min(count, numerator, denominator) < 0
        or numerator > denominator
        or count != denominator
        or vacuous != (denominator == 0)
    ):
        raise ValueError("Q5 beneficial evidence accounting is inconsistent")
    if denominator == 0:
        if capture is not None:
            raise ValueError("Q5 empty beneficial capture must be null")
        return count, None
    expected_capture = round(numerator / denominator, 6)
    if _number(capture, "beneficial value capture") != expected_capture:
        raise ValueError("Q5 beneficial capture ratio is inconsistent")
    return count, expected_capture


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Q5 claim readiness {label} is missing")
    return float(value)
