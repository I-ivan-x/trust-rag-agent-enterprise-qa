"""Q5 isolated environment transitions and assertion-based outcome grading."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.govern.conditions import GovernanceAction
from app.govern.sinks import ActionRecord
from app.schemas.q5_task import Q5EnvironmentState

Q5_SIDE_EFFECT_ACTIONS = frozenset(
    {
        GovernanceAction.flag_stale,
        GovernanceAction.open_remediation_ticket,
        GovernanceAction.send_alert,
    }
)
_MISSING = object()
_PATH_PART = re.compile(r"([^.[\]]+)|\[(\d+)\]")
Q5TransitionKind = Literal[
    "committed",
    "pending_approval",
    "escalated",
    "dropped",
    "no_op",
    "invalid",
]


class Q5OutcomeEnvironmentState(BaseModel):
    """Per-trial environment copy used only for observable final-state grading."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    environment_ref: str = Field(min_length=1)
    policy_exceptions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    change_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    incident_impacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    records: list[dict[str, Any]] = Field(default_factory=list)
    pending_queue: list[dict[str, Any]] = Field(default_factory=list)
    tool_faults: dict[str, dict[str, Any]] | None = None

    @model_validator(mode="after")
    def _unique_record_ids(self) -> Q5OutcomeEnvironmentState:
        ids = [
            str(item["record_id"])
            for item in [*self.records, *self.pending_queue]
            if item.get("record_id") is not None
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("Q5 outcome record_id values must be unique")
        return self


class Q5EnvironmentTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: GovernanceAction
    approval_state: str
    transition: Q5TransitionKind
    valid: bool
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    record_id: str | None = None
    environment_before_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_after_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_side_effect: bool = False
    pending_side_effect: bool = False


class Q5AssertionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assertion_index: int = Field(ge=0)
    path: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    passed: bool
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    expected: Any = None
    actual: Any = None
    actual_missing: bool = False


class Q5FinalStateGrade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_success: bool
    passed_assertions: int = Field(ge=0)
    assertion_count: int = Field(ge=0)
    assertion_results: list[Q5AssertionResult] = Field(default_factory=list)


def q5_outcome_environment_from_runtime(
    state: Q5EnvironmentState,
) -> Q5OutcomeEnvironmentState:
    """Create a deep, isolated outcome state without mutating runtime tool state."""

    return Q5OutcomeEnvironmentState(
        environment_ref=state.environment_ref,
        policy_exceptions=deepcopy(state.policy_exceptions),
        change_states=deepcopy(state.change_states),
        incident_impacts=deepcopy(state.incident_impacts),
        records=deepcopy(state.initial_records),
        pending_queue=deepcopy(state.pending_queue),
        tool_faults=deepcopy(state.tool_faults),
    )


def apply_q5_environment_transition(
    before: Q5OutcomeEnvironmentState,
    *,
    action: GovernanceAction,
    record: ActionRecord | None,
) -> tuple[Q5OutcomeEnvironmentState, Q5EnvironmentTransition]:
    """Apply one validated terminal result to an isolated environment copy."""

    records = deepcopy(before.records)
    pending_queue = deepcopy(before.pending_queue)
    valid = True
    committed = False
    pending = False
    reason_code = "state_unchanged"
    transition: Q5TransitionKind = "no_op"
    approval_state = record.approval_state if record is not None else "none"
    existing_record_ids = {
        str(item["record_id"])
        for item in [*records, *pending_queue]
        if item.get("record_id") is not None
    }

    if action is GovernanceAction.no_op:
        if record is not None:
            valid = False
            reason_code = "no_op_record_forbidden"
            transition = "invalid"
        else:
            reason_code = "no_op"
    elif action is GovernanceAction.escalate_to_human:
        if record is not None and (
            record.action is not action or record.approval_state != "escalated"
        ):
            valid = False
            reason_code = "invalid_escalation_record"
            transition = "invalid"
        else:
            transition = "escalated"
            reason_code = "escalated_without_side_effect"
    elif action in Q5_SIDE_EFFECT_ACTIONS:
        if record is None or record.action is not action:
            valid = False
            reason_code = "missing_or_mismatched_record"
            transition = "invalid"
        elif record.record_id in existing_record_ids:
            valid = False
            reason_code = "duplicate_record_id"
            transition = "invalid"
        elif record.approval_state == "committed":
            records.append(record.model_dump(mode="json"))
            transition = "committed"
            reason_code = "committed_record_added"
            committed = True
        elif record.approval_state == "pending_approval":
            pending_queue.append(record.model_dump(mode="json"))
            transition = "pending_approval"
            reason_code = "pending_queue_added"
            pending = True
        elif record.approval_state == "dropped":
            transition = "dropped"
            reason_code = "dropped_without_side_effect"
        else:
            valid = False
            reason_code = "invalid_side_effect_approval_state"
            transition = "invalid"
    else:  # pragma: no cover - GovernanceAction is currently exhaustive above
        valid = False
        reason_code = "unsupported_action"
        transition = "invalid"

    if not valid:
        records = deepcopy(before.records)
        pending_queue = deepcopy(before.pending_queue)
        committed = False
        pending = False

    after = Q5OutcomeEnvironmentState.model_validate(
        {
            **before.model_dump(mode="json"),
            "records": records,
            "pending_queue": pending_queue,
        }
    )
    before_hash = q5_environment_hash(before)
    after_hash = q5_environment_hash(after)
    event = Q5EnvironmentTransition(
        action=action,
        approval_state=approval_state,
        transition=transition,
        valid=valid,
        reason_code=reason_code,
        record_id=record.record_id if record is not None else None,
        environment_before_sha256=before_hash,
        environment_after_sha256=after_hash,
        committed_side_effect=committed,
        pending_side_effect=pending,
    )
    return after, event


def grade_q5_final_state(
    assertions: list[dict[str, Any]],
    *,
    before: Q5OutcomeEnvironmentState | dict[str, Any],
    after: Q5OutcomeEnvironmentState | dict[str, Any],
) -> Q5FinalStateGrade:
    """Grade only machine-observable final state, never agent reason text."""

    before_payload = _payload(before)
    after_payload = _payload(after)
    results = [
        _grade_assertion(index, assertion, before_payload, after_payload)
        for index, assertion in enumerate(assertions)
    ]
    passed = sum(result.passed for result in results)
    return Q5FinalStateGrade(
        task_success=bool(results) and passed == len(results),
        passed_assertions=passed,
        assertion_count=len(results),
        assertion_results=results,
    )


def q5_environment_hash(state: Q5OutcomeEnvironmentState | dict[str, Any]) -> str:
    payload = _payload(state)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _grade_assertion(
    index: int,
    assertion: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
) -> Q5AssertionResult:
    path = assertion.get("path")
    operator = assertion.get("operator")
    if not isinstance(path, str) or not path or not isinstance(operator, str):
        return Q5AssertionResult(
            assertion_index=index,
            path=str(path or "invalid"),
            operator=str(operator or "invalid"),
            passed=False,
            reason_code="invalid_assertion_schema",
        )

    actual = _resolve_path(after, path)
    prior = _resolve_path(before, path)
    expected = assertion.get("value", assertion.get("count"))
    normalized = operator.strip().lower()
    passed = False
    reason_code = "assertion_failed"
    value_operators = {"equals", "eq", "not_equals", "ne", "contains", "not_contains"}
    if normalized in value_operators and "value" not in assertion:
        return Q5AssertionResult(
            assertion_index=index,
            path=path,
            operator=normalized,
            passed=False,
            reason_code="invalid_assertion_schema",
            actual=None if actual is _MISSING else actual,
            actual_missing=actual is _MISSING,
        )
    if normalized in {"length_equals", "count_equals"} and expected is None:
        return Q5AssertionResult(
            assertion_index=index,
            path=path,
            operator=normalized,
            passed=False,
            reason_code="invalid_assertion_schema",
            actual=None if actual is _MISSING else actual,
            actual_missing=actual is _MISSING,
        )

    if normalized in {"equals", "eq"}:
        passed = actual is not _MISSING and actual == expected
    elif normalized in {"not_equals", "ne"}:
        passed = actual is not _MISSING and actual != expected
    elif normalized == "unchanged":
        passed = actual is not _MISSING and prior is not _MISSING and actual == prior
    elif normalized == "changed":
        passed = actual is not _MISSING and prior is not _MISSING and actual != prior
    elif normalized == "exists":
        passed = actual is not _MISSING
    elif normalized == "absent":
        passed = actual is _MISSING
    elif normalized == "contains":
        passed = actual is not _MISSING and _contains(actual, expected)
    elif normalized == "not_contains":
        passed = actual is not _MISSING and not _contains(actual, expected)
    elif normalized in {"length_equals", "count_equals"}:
        count = _matching_count(actual, assertion.get("where"))
        passed = count is not None and count == expected
        actual = count if count is not None else actual
    else:
        reason_code = "unsupported_operator"
        return Q5AssertionResult(
            assertion_index=index,
            path=path,
            operator=normalized,
            passed=False,
            reason_code=reason_code,
            expected=expected,
            actual=None if actual is _MISSING else actual,
            actual_missing=actual is _MISSING,
        )

    if passed:
        reason_code = "assertion_passed"
    return Q5AssertionResult(
        assertion_index=index,
        path=path,
        operator=normalized,
        passed=passed,
        reason_code=reason_code,
        expected=expected,
        actual=None if actual is _MISSING else actual,
        actual_missing=actual is _MISSING,
    )


def _resolve_path(payload: Any, path: str) -> Any:
    current = payload
    parts = [
        key if key else int(index)
        for key, index in _PATH_PART.findall(path)
    ]
    if not parts:
        return _MISSING
    for part in parts:
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                return _MISSING
            current = current[part]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, list):
        return any(_subset_match(item, expected) for item in actual)
    if isinstance(actual, dict):
        if isinstance(expected, dict):
            return _subset_match(actual, expected)
        return expected in actual
    if isinstance(actual, str) and isinstance(expected, str):
        return expected in actual
    return False


def _subset_match(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _subset_match(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and all(
            any(_subset_match(item, wanted) for item in actual) for wanted in expected
        )
    return actual == expected


def _matching_count(actual: Any, where: Any) -> int | None:
    if not isinstance(actual, (list, dict, str)):
        return None
    if where is None:
        return len(actual)
    if not isinstance(actual, list) or not isinstance(where, dict):
        return None
    return sum(_subset_match(item, where) for item in actual)


def _payload(state: Q5OutcomeEnvironmentState | dict[str, Any]) -> dict[str, Any]:
    if isinstance(state, Q5OutcomeEnvironmentState):
        return state.model_dump(mode="json")
    return deepcopy(state)
