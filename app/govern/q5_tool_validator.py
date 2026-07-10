"""Q5 read-only tool schema and argument-provenance validation."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.govern.q5_context import (
    Q5DecisionContext,
    assert_q5_no_gold_or_control_fields,
)
from app.schemas.q5_task import Q5ObservationTool, Q5TaskInput

_REFERENCE_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*:[a-z0-9_./:-]+", re.IGNORECASE)


class LookupPolicyExceptionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_ref: str = Field(min_length=1)
    policy_ref: str = Field(min_length=1)


class InspectChangeStateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    change_ref: str = Field(min_length=1)


class InspectIncidentImpactArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_ref: str = Field(min_length=1)


class Q5ValidatedToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: Q5ObservationTool
    args: dict[str, str]


class Q5ToolValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    reason_code: Literal[
        "allowed",
        "tool_not_allowed",
        "schema_invalid",
        "new_entity_injection",
        "forbidden_control_field",
    ]
    call: Q5ValidatedToolCall | None = None
    rejected_values: list[str] = Field(default_factory=list)


_ARG_MODEL_BY_TOOL: Mapping[Q5ObservationTool, type[BaseModel]] = {
    Q5ObservationTool.lookup_policy_exception: LookupPolicyExceptionArgs,
    Q5ObservationTool.inspect_change_state: InspectChangeStateArgs,
    Q5ObservationTool.inspect_incident_impact: InspectIncidentImpactArgs,
}


def validate_q5_tool_call(
    *,
    tool: Q5ObservationTool,
    args: Mapping[str, Any],
    task: Q5TaskInput,
    context: Q5DecisionContext,
) -> Q5ToolValidationResult:
    """Reject any tool/entity not grounded in the current authorized runtime state."""

    try:
        assert_q5_no_gold_or_control_fields(args)
    except ValueError:
        return Q5ToolValidationResult(
            allowed=False,
            reason_code="forbidden_control_field",
        )

    if tool not in task.available_tools or tool not in context.available_tools:
        return Q5ToolValidationResult(allowed=False, reason_code="tool_not_allowed")

    try:
        parsed = _ARG_MODEL_BY_TOOL[tool].model_validate(dict(args))
    except (KeyError, ValidationError):
        return Q5ToolValidationResult(allowed=False, reason_code="schema_invalid")

    normalized = {
        key: str(value)
        for key, value in parsed.model_dump(mode="json").items()
    }
    allowed_values = q5_allowed_tool_argument_values(task=task, context=context)
    rejected = sorted({value for value in normalized.values() if value not in allowed_values})
    if rejected:
        return Q5ToolValidationResult(
            allowed=False,
            reason_code="new_entity_injection",
            rejected_values=rejected,
        )
    return Q5ToolValidationResult(
        allowed=True,
        reason_code="allowed",
        call=Q5ValidatedToolCall(tool=tool, args=normalized),
    )


def q5_allowed_tool_argument_values(
    *,
    task: Q5TaskInput,
    context: Q5DecisionContext,
) -> frozenset[str]:
    values = {str(value) for value in task.resource_refs}
    values.update(str(value) for value in context.resource_refs)
    for evidence in context.authorized_evidence:
        values.update({evidence.chunk_id, evidence.doc_id})
        values.update(_REFERENCE_PATTERN.findall(evidence.text_excerpt))
        if evidence.relation_summary:
            values.update(_strings_from_relation(evidence.relation_summary))
    for observation in context.observations:
        values.update(_nested_strings(observation.observation))
    return frozenset(value for value in values if value)


def _strings_from_relation(summary: str) -> set[str]:
    try:
        parsed = json.loads(summary)
    except (json.JSONDecodeError, TypeError):
        return set(_REFERENCE_PATTERN.findall(summary))
    return _nested_strings(parsed)


def _nested_strings(value: Any) -> set[str]:
    strings: set[str] = set()
    if isinstance(value, str):
        strings.add(value)
    elif isinstance(value, Mapping):
        for nested in value.values():
            strings.update(_nested_strings(nested))
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for nested in value:
            strings.update(_nested_strings(nested))
    return strings
