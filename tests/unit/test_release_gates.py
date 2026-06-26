"""Q4-P7 tests for absolute release hard gates (SPEC_Q4_P6_P7 §3).

Synthetic summaries are CI-safe (no network, no real run). One test loads the real
q4-p5 summary from disk when present to confirm the calibrated headline run passes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_release_gates import evaluate_gates

REAL_Q4P5 = Path("data/eval_runs/q4-p5-selection-calibrated/summary.json")


def _summary(
    *,
    f11=0,
    f13=0,
    mock_used=False,
    vector_unavailable=False,
    rule_triad=True,
    rule_eligible=True,
) -> dict:
    return {
        "mock_used": mock_used,
        "vector_unavailable": vector_unavailable,
        "governance_attribution": {
            "failure_taxonomy": {
                "F11_action_without_evidence": f11,
                "F13_missed_escalation_unauth": f13,
            }
        },
        "governance_headline_eligible_by_system": {"final_governed_rule": rule_eligible},
        "governance_metrics": {
            "by_system": {"final_governed_rule": {"anti_gaming_triad_ok": rule_triad}}
        },
    }


def _failed(results):
    return {r.name for r in results if not r.passed}


def test_gate_trips_on_f11_nonzero() -> None:
    assert "G1_F11_zero" in _failed(evaluate_gates(_summary(f11=1)))


def test_gate_trips_on_f13_nonzero() -> None:
    assert "G2_F13_zero" in _failed(evaluate_gates(_summary(f13=2)))


def test_gate_trips_on_triad_false_headline() -> None:
    # headline-eligible but triad False must fail G3
    assert "G3_triad_gates_headline" in _failed(
        evaluate_gates(_summary(rule_triad=False, rule_eligible=True))
    )


def test_gate_trips_on_mock_headline() -> None:
    assert "G4_mock_no_headline" in _failed(
        evaluate_gates(_summary(mock_used=True, rule_eligible=True))
    )


def test_gate_trips_on_vector_unavailable_headline() -> None:
    assert "G5_vector_unavailable_no_headline" in _failed(
        evaluate_gates(_summary(vector_unavailable=True, rule_eligible=True))
    )


def test_leakage_gate_trips_on_blocking_flag() -> None:
    leakage = {"blocking_flags": [{"case_id": "x", "flag_type": "high_title_overlap"}]}
    assert "GL_leakage_zero_blocking" in _failed(
        evaluate_gates(_summary(), leakage_report=leakage)
    )
    # zero blocking flags passes
    assert "GL_leakage_zero_blocking" not in _failed(
        evaluate_gates(_summary(), leakage_report={"blocking_flags": []})
    )


def test_gate_passes_clean_summary() -> None:
    assert _failed(evaluate_gates(_summary())) == set()


@pytest.mark.skipif(not REAL_Q4P5.is_file(), reason="q4-p5 real summary not present")
def test_gate_passes_clean_q4p5() -> None:
    summary = json.loads(REAL_Q4P5.read_text(encoding="utf-8"))
    results = evaluate_gates(summary)
    assert _failed(results) == set(), f"q4-p5 should pass all gates; failed={_failed(results)}"
