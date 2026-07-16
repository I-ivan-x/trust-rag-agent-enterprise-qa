"""Independent Q5 value-frontier claim-readiness evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

Q5_CLAIM_READINESS_SCHEMA = "q5-claim-readiness-i"


def evaluate_q5_claim_readiness(
    run_summary: Mapping[str, Any],
    value_summary: Mapping[str, Any],
    symbolic_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare Hybrid evidence with the independently executed symbolic control."""

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
        "hybrid_observation_planning_llm_calls": 0,
        "hybrid_semantic_binding_llm_calls": 36,
    }
    checks = {
        "semantic_headroom": hybrid_semantic >= symbolic_semantic + 0.1,
        "within_policy_headroom": hybrid_within >= symbolic_within + 0.166667,
        "cross_policy_headroom": hybrid_cross >= symbolic_cross + 0.166667,
        "beneficial_value_capture": _number(
            value_summary.get("beneficial_value_capture"),
            "beneficial value capture",
        )
        >= 1.0,
        "harmful_terminal_llm_exposure": value_summary.get(
            "harmful_terminal_llm_exposure"
        )
        == 0,
        "hybrid_oracle_regret": _number(
            value_summary.get("hybrid_oracle_regret"),
            "Hybrid oracle regret",
        )
        <= 0.027778,
        "hybrid_observation_planning_llm_calls": value_summary.get(
            "hybrid_observation_planning_llm_calls"
        )
        == 0,
        "hybrid_semantic_binding_llm_calls": value_summary.get(
            "hybrid_semantic_binding_llm_calls"
        )
        == 36,
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
    blockers.extend(name for name, passed in checks.items() if not passed)
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
            "beneficial_value_capture": value_summary["beneficial_value_capture"],
            "harmful_terminal_llm_exposure": value_summary[
                "harmful_terminal_llm_exposure"
            ],
            "hybrid_oracle_regret": value_summary["hybrid_oracle_regret"],
            "hybrid_observation_planning_llm_calls": value_summary[
                "hybrid_observation_planning_llm_calls"
            ],
            "hybrid_semantic_binding_llm_calls": value_summary[
                "hybrid_semantic_binding_llm_calls"
            ],
        },
    }


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Q5 claim readiness {label} is missing")
    return float(value)
