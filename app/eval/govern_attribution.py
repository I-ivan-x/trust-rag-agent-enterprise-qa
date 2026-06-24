from __future__ import annotations

from typing import Any

from app.eval.govern_metrics import (
    ACTION_METRIC_TAG,
    ESCALATE_ACTION,
    SIDE_EFFECT_ACTIONS,
)
from app.govern.conditions import GovernanceAction

GOVERNANCE_ACTIONS = tuple(action.value for action in GovernanceAction)


def compute_governance_attribution(
    trace_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Compute per-action governance attribution and F10-F13 counts."""

    rows = _merge_governance_rows(trace_rows, result_rows)
    if not rows:
        return None

    per_action = {
        action: {
            "proposed_count": 0,
            "correct_count": 0,
            "false_trigger_count": 0,
            "blocked_count": 0,
        }
        for action in GOVERNANCE_ACTIONS
    }
    failures = {
        "F10_wrong_action_selected": 0,
        "F11_action_without_evidence": 0,
        "F12_over_escalation": 0,
        "F13_missed_escalation_unauth": 0,
    }
    systems: set[str] = set()

    for row in rows:
        system_name = _string(_field(row, "system_name"))
        if system_name:
            systems.add(system_name)
        proposed_action = _action(row, "proposed_action")
        gold_action = _action(row, "gold_action")

        if proposed_action in per_action:
            per_action[proposed_action]["proposed_count"] += 1
            if proposed_action == gold_action:
                per_action[proposed_action]["correct_count"] += 1
            else:
                per_action[proposed_action]["false_trigger_count"] += 1
            if _blocked(row, proposed_action):
                per_action[proposed_action]["blocked_count"] += 1

        if (
            proposed_action != gold_action
            and proposed_action in SIDE_EFFECT_ACTIONS
            and gold_action in SIDE_EFFECT_ACTIONS
        ):
            failures["F10_wrong_action_selected"] += 1
        if (
            _string(_field(row, "evidence_decision")) == "insufficient"
            and _executed_side_effect(row)
        ):
            failures["F11_action_without_evidence"] += 1
        if gold_action != ESCALATE_ACTION and proposed_action == ESCALATE_ACTION:
            failures["F12_over_escalation"] += 1
        if _field(row, "authorized") is False and _executed_side_effect(row):
            failures["F13_missed_escalation_unauth"] += 1

    return {
        "metric_type": ACTION_METRIC_TAG,
        "metric_tags": [ACTION_METRIC_TAG],
        "governance_systems": sorted(systems),
        "per_action": per_action,
        "failure_taxonomy": failures,
        "headline_policy": (
            "Governance attribution is an action_metric diagnostic view and is not "
            "merged into grounded retrieval/answer headline metrics."
        ),
    }


def _merge_governance_rows(
    trace_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    trace_by_key = {
        _row_key(row): row
        for row in trace_rows
        if _row_key(row) and _field(row, "proposed_action") is not None
    }
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    for result in result_rows:
        if _field(result, "proposed_action") is None and _field(result, "gold_action") is None:
            continue
        key = _row_key(result)
        trace = trace_by_key.get(key) if key else None
        merged = {**(trace or {}), **result}
        rows.append(merged)
        if key:
            seen_keys.add(key)

    for key, trace in trace_by_key.items():
        if key not in seen_keys:
            rows.append(trace)

    return rows


def _row_key(row: dict[str, Any]) -> tuple[str, str, str, str] | None:
    case_id = _string(_field(row, "case_id"))
    system_name = _string(_field(row, "system_name"))
    run_index = _string(_field(row, "run_index"))
    split = _string(_field(row, "eval_split") or _field(row, "split"))
    if not case_id or not system_name:
        return None
    return (split, case_id, system_name, run_index)


def _blocked(row: dict[str, Any], proposed_action: str) -> bool:
    forced_action = _action(row, "forced_action")
    return _field(row, "validator_ok") is False or bool(
        forced_action and forced_action != proposed_action
    )


def _executed_side_effect(row: dict[str, Any]) -> bool:
    value = _field(row, "executed_side_effect")
    if isinstance(value, bool):
        return value
    return (
        _string(_field(row, "approval_state")) == "committed"
        and _action(row, "proposed_action") in SIDE_EFFECT_ACTIONS
    )


def _action(row: dict[str, Any], name: str) -> str:
    return _string(_field(row, name))


def _field(row: Any, name: str) -> Any:
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def _string(value: Any) -> str:
    return str(value) if value is not None else ""
