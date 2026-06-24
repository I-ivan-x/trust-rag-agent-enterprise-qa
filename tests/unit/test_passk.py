from __future__ import annotations

import pytest

from app.eval.passk import compute_passk


def test_compute_passk_attempt_mean_all_pass_and_sequence_consistency() -> None:
    results = [
        _result("case-a", "sys-a", 1, True),
        _result("case-a", "sys-a", 2, True),
        _result("case-a", "sys-a", 3, True),
        _result("case-b", "sys-a", 1, True),
        _result("case-b", "sys-a", 2, False),
        _result("case-b", "sys-a", 3, True),
    ]
    traces = [
        _trace("case-a", "sys-a", 1, ["rewrite_query"]),
        _trace("case-a", "sys-a", 2, ["rewrite_query"]),
        _trace("case-a", "sys-a", 3, ["rewrite_query"]),
        _trace("case-b", "sys-a", 1, ["rewrite_query"]),
        _trace("case-b", "sys-a", 2, ["refuse_with_explanation"]),
        _trace("case-b", "sys-a", 3, ["rewrite_query"]),
    ]

    summary = compute_passk(results, traces, k=3)

    metrics = summary["by_system"]["sys-a"]
    assert metrics["case_count"] == 2
    assert metrics["attempt_count"] == 6
    assert metrics["pass_1_attempt_mean"] == pytest.approx(5 / 6, abs=0.0001)
    assert metrics["pass_1_first_run"] == 1.0
    assert metrics["pass_3"] == 0.5
    assert metrics["action_sequence_consistency"] == 0.5


def test_compute_passk_treats_empty_baseline_sequence_as_consistent() -> None:
    results = [_result("case-a", "baseline", index, True) for index in (1, 2, 3)]
    traces = [_trace("case-a", "baseline", index, []) for index in (1, 2, 3)]

    summary = compute_passk(results, traces, k=3)

    assert summary["by_system"]["baseline"]["action_sequence_consistency"] == 1.0


def _result(
    case_id: str,
    system_name: str,
    run_index: int,
    grounded: bool,
) -> dict:
    return {
        "eval_split": "fixture",
        "case_id": case_id,
        "system_name": system_name,
        "run_index": run_index,
        "grounded_correct": grounded,
    }


def _trace(
    case_id: str,
    system_name: str,
    run_index: int,
    action_sequence: list[str],
) -> dict:
    return {
        "split": "fixture",
        "case_id": case_id,
        "system_name": system_name,
        "run_index": run_index,
        "action_sequence": action_sequence,
    }
