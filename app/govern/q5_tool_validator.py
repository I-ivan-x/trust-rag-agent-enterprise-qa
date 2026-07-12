"""Q5 read-only tool schema and argument-provenance validation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.govern.q5_context import (
    Q5_CHANGE_REF_PATTERN,
    Q5_POLICY_REF_PATTERN,
    Q5_REFERENCE_SUFFIX_PATTERN,
    Q5_RESOURCE_REF_PATTERN,
    Q5DecisionContext,
    assert_q5_no_gold_or_control_fields,
)
from app.schemas.q5_task import Q5ObservationTool, Q5TaskInput

_REFERENCE_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9_.:/-])"
    rf"(?:resource|policy|change):{Q5_REFERENCE_SUFFIX_PATTERN}"
    rf"(?![A-Za-z0-9_.:/-])"
)
_REFERENCE_FIELD_PATTERNS: Mapping[str, re.Pattern[str]] = {
    "resource_ref": re.compile(Q5_RESOURCE_REF_PATTERN),
    "policy_ref": re.compile(Q5_POLICY_REF_PATTERN),
    "change_ref": re.compile(Q5_CHANGE_REF_PATTERN),
}
_REFERENCE_PATTERNS = tuple(_REFERENCE_FIELD_PATTERNS.values())


class LookupPolicyExceptionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_ref: str = Field(pattern=Q5_RESOURCE_REF_PATTERN)
    policy_ref: str = Field(pattern=Q5_POLICY_REF_PATTERN)


class InspectChangeStateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    change_ref: str = Field(pattern=Q5_CHANGE_REF_PATTERN)


class InspectIncidentImpactArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_ref: str = Field(pattern=Q5_RESOURCE_REF_PATTERN)


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


_ARG_MODEL_BY_TOOL: Mapping[Q5ObservationTool, type[BaseModel]] = MappingProxyType(
    {
        Q5ObservationTool.lookup_policy_exception: LookupPolicyExceptionArgs,
        Q5ObservationTool.inspect_change_state: InspectChangeStateArgs,
        Q5ObservationTool.inspect_incident_impact: InspectIncidentImpactArgs,
    }
)


def q5_tool_args_model(tool: Q5ObservationTool) -> type[BaseModel]:
    """Return the sole Pydantic source of truth for a tool's argument contract."""

    return _ARG_MODEL_BY_TOOL[tool]


def q5_tool_contracts(context: Q5DecisionContext) -> list[dict[str, Any]]:
    """Build prompt contracts directly from the runtime validator models."""

    grounded = q5_grounded_tool_argument_values(context=context)
    contracts: list[dict[str, Any]] = []
    for tool in context.available_tools:
        schema = q5_tool_args_model(tool).model_json_schema()
        if schema.get("additionalProperties") is not False:
            raise RuntimeError(f"Q5 tool schema must forbid extra args: {tool.value}")
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise RuntimeError(f"Q5 tool schema is incomplete: {tool.value}")
        contracts.append(
            {
                "tool": tool.value,
                "args_schema": schema,
                "grounded_reference_values": {
                    field: sorted(grounded.get(field, frozenset()))
                    for field in properties
                },
            }
        )
    return contracts


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
        parsed = q5_tool_args_model(tool).model_validate(dict(args))
    except (KeyError, ValidationError):
        return Q5ToolValidationResult(allowed=False, reason_code="schema_invalid")

    normalized = {
        key: str(value)
        for key, value in parsed.model_dump(mode="json").items()
    }
    allowed_values = q5_grounded_tool_argument_values(task=task, context=context)
    rejected = sorted(
        {
            value
            for field, value in normalized.items()
            if value not in allowed_values.get(field, frozenset())
        }
    )
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
    """Backward-compatible flattened view of field-aware grounded references."""

    values_by_field = q5_grounded_tool_argument_values(task=task, context=context)
    return frozenset(
        value for values in values_by_field.values() for value in values
    )


def q5_grounded_tool_argument_values(
    *,
    context: Q5DecisionContext,
    task: Q5TaskInput | None = None,
) -> Mapping[str, frozenset[str]]:
    """Return only valid references, grouped by the argument field they may fill."""

    values = _valid_references(task.resource_refs if task is not None else [])
    values.update(_valid_references(context.resource_refs))
    for evidence in context.authorized_evidence:
        values.update(_references_from_text(evidence.text_excerpt))
        if evidence.relation_summary:
            values.update(_references_from_relation(evidence.relation_summary))
    for observation in context.observations:
        values.update(_references_from_fields(observation.observation))
    return MappingProxyType(
        {
            field: frozenset(
                value for value in values if pattern.fullmatch(value)
            )
            for field, pattern in _REFERENCE_FIELD_PATTERNS.items()
        }
    )


def _references_from_relation(summary: str) -> set[str]:
    try:
        parsed = json.loads(summary)
    except (json.JSONDecodeError, TypeError):
        return set()
    return _references_from_fields(parsed)


def _references_from_fields(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            pattern = _REFERENCE_FIELD_PATTERNS.get(str(key))
            if pattern is not None and isinstance(nested, str) and pattern.fullmatch(nested):
                references.add(nested)
            elif isinstance(nested, (Mapping, list, tuple)):
                references.update(_references_from_fields(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            references.update(_references_from_fields(nested))
    return references


def _references_from_text(text: str) -> set[str]:
    return {match.group(0) for match in _REFERENCE_PATTERN.finditer(text)}


def _valid_references(values: list[str]) -> set[str]:
    return {str(value) for value in values if _is_valid_reference(str(value))}


def _is_valid_reference(value: str) -> bool:
    return any(pattern.fullmatch(value) for pattern in _REFERENCE_PATTERNS)
