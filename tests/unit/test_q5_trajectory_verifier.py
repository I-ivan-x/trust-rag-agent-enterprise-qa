from __future__ import annotations

import pytest

from app.eval.q5_runner import _index_trajectory_rows

TRIAL_KEY = "case-1|q5_llm_agent|1"


def test_q5_trajectory_verifier_accepts_tool_rejection_and_safe_terminal_same_step() -> None:
    rows = [
        _row(step=1, event_type="tool_rejected"),
        _row(step=1, event_type="terminal"),
    ]

    grouped = _index_trajectory_rows(
        rows,
        expected_keys={TRIAL_KEY},
        label="trajectory.jsonl",
    )

    assert [item["event_type"] for item in grouped[TRIAL_KEY]] == [
        "tool_rejected",
        "terminal",
    ]


def test_q5_trajectory_verifier_accepts_timeout_terminal_on_next_step() -> None:
    rows = [
        _row(step=1, event_type="observation"),
        _row(step=2, event_type="terminal"),
    ]

    grouped = _index_trajectory_rows(
        rows,
        expected_keys={TRIAL_KEY},
        label="trajectory.jsonl",
    )

    assert [item["step_index"] for item in grouped[TRIAL_KEY]] == [1, 2]


def test_q5_trajectory_verifier_rejects_unapproved_same_step_pair() -> None:
    rows = [
        _row(step=1, event_type="observation"),
        _row(step=1, event_type="terminal"),
    ]

    with pytest.raises(ValueError, match="invalid same-step event pair"):
        _index_trajectory_rows(
            rows,
            expected_keys={TRIAL_KEY},
            label="trajectory.jsonl",
        )


def _row(*, step: int, event_type: str) -> dict[str, object]:
    return {
        "case_id": "case-1",
        "system": "q5_llm_agent",
        "run_index": 1,
        "step_index": step,
        "event_type": event_type,
    }
