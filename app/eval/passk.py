from __future__ import annotations

from collections import defaultdict
from typing import Any


def compute_passk(
    result_rows: list[dict[str, Any]],
    trace_rows: list[dict[str, Any]],
    *,
    k: int,
) -> dict[str, Any]:
    """Compute pass^1/pass^k and cross-run action-sequence consistency.

    pass_1_attempt_mean is the mean grounded_correct over all k attempts. The
    first-run value is kept separately so reports can avoid depending on an
    arbitrary repeat while still exposing the literal first pass.
    """

    if k <= 0:
        raise ValueError("k must be positive")

    results_by_system_case: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in result_rows:
        system = _string(row.get("system_name"))
        case_key = _case_key(row)
        if not system or not case_key:
            continue
        results_by_system_case[(system, case_key)].append(row)

    traces_by_system_case: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in trace_rows:
        system = _string(row.get("system_name"))
        case_key = _case_key(row)
        if not system or not case_key:
            continue
        traces_by_system_case[(system, case_key)].append(row)

    systems = sorted({system for system, _ in results_by_system_case})
    by_system: dict[str, dict[str, Any]] = {}
    for system in systems:
        keys = sorted(key for key in results_by_system_case if key[0] == system)
        complete_keys = [
            key for key in keys if len(results_by_system_case[key]) >= k
        ]
        total_attempts = len(complete_keys) * k
        passed_attempts = 0
        first_run_passed = 0
        all_run_passed = 0
        consistent_sequences = 0

        for key in complete_keys:
            rows = _sort_by_run_index(results_by_system_case[key])[:k]
            pass_values = [row.get("grounded_correct") is True for row in rows]
            passed_attempts += sum(pass_values)
            if pass_values[0]:
                first_run_passed += 1
            if all(pass_values):
                all_run_passed += 1

            traces = _sort_by_run_index(traces_by_system_case.get(key, []))[:k]
            sequences = [_action_sequence(trace) for trace in traces]
            if len(sequences) == k and len({tuple(seq) for seq in sequences}) <= 1:
                consistent_sequences += 1

        case_count = len(complete_keys)
        by_system[system] = {
            "k": k,
            "case_count": case_count,
            "complete_case_count": case_count,
            "attempt_count": total_attempts,
            "pass_1_attempt_mean": _ratio(passed_attempts, total_attempts),
            "pass_1_first_run": _ratio(first_run_passed, case_count),
            f"pass_{k}": _ratio(all_run_passed, case_count),
            "action_sequence_consistency": _ratio(consistent_sequences, case_count),
        }

    return {
        "k": k,
        "by_system": by_system,
        "notes": {
            "pass_1_attempt_mean": "Mean grounded_correct over all repeated attempts.",
            "pass_k": "Case passes only when every repeated attempt is grounded_correct.",
            "action_sequence_consistency": (
                "Share of cases whose action_sequence is identical across all repeats."
            ),
        },
    }


def _sort_by_run_index(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: int(row.get("run_index") or 0))


def _case_key(row: dict[str, Any]) -> str:
    split = _string(row.get("eval_split") or row.get("split"))
    case_id = _string(row.get("case_id"))
    return f"{split}:{case_id}" if split and case_id else case_id


def _action_sequence(trace: dict[str, Any]) -> list[str]:
    sequence = trace.get("action_sequence")
    if isinstance(sequence, list):
        return [str(item) for item in sequence]
    trajectory = trace.get("action_trajectory")
    if isinstance(trajectory, list):
        return [
            str(step.get("chosen_action"))
            for step in trajectory
            if isinstance(step, dict) and step.get("chosen_action") is not None
        ]
    return []


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _string(value: Any) -> str:
    return str(value) if value is not None else ""
