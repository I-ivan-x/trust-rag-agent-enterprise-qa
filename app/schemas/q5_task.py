"""Q5 task, environment, and grader-only gold contracts.

These models intentionally do not reuse ``EvalCase``. Q5 runtime inputs and
grader labels are physically separate objects so execution code cannot receive
gold fields by construction.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequestedCapability(StrEnum):
    document_maintenance = "document_maintenance"
    remediation_management = "remediation_management"
    incident_response = "incident_response"
    investigate = "investigate"


class Q5ObservationTool(StrEnum):
    lookup_policy_exception = "lookup_policy_exception"
    inspect_change_state = "inspect_change_state"
    inspect_incident_impact = "inspect_incident_impact"


class Q5Stratum(StrEnum):
    deterministic = "deterministic"
    semantic = "semantic"
    adversarial = "adversarial"


class Q5ActorClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1)
    clearance: str = Field(min_length=1)
    department: str | None = None


class Q5TaskInput(BaseModel):
    """Runtime-visible Q5 case input. Gold-only fields are rejected as extras."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    actor: Q5ActorClaims
    requested_capability: RequestedCapability
    resource_refs: list[str] = Field(default_factory=list)
    available_tools: list[Q5ObservationTool] = Field(default_factory=list)
    corpus_namespace: str = Field(min_length=1)
    environment_ref: str = Field(min_length=1)
    max_observation_steps: int = Field(ge=0, le=2)
    max_terminal_actions: Literal[1]

    @model_validator(mode="after")
    def _reject_duplicate_runtime_refs(self) -> Q5TaskInput:
        _require_unique(self.resource_refs, field="resource_refs")
        _require_unique(self.available_tools, field="available_tools")
        return self


class Q5EnvironmentState(BaseModel):
    """Tool-runtime state; controllers must access it only through typed tools."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    environment_ref: str = Field(min_length=1)
    policy_exceptions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    change_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    incident_impacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    initial_records: list[dict[str, Any]] = Field(default_factory=list)
    pending_queue: list[dict[str, Any]] = Field(default_factory=list)
    tool_faults: dict[str, dict[str, Any]] | None = None


class Q5Gold(BaseModel):
    """Grader-only Q5 labels. This type is never accepted by runtime loaders."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    stratum: Q5Stratum
    allowed_terminal_actions: list[str] = Field(min_length=1)
    forbidden_terminal_actions: list[str] = Field(default_factory=list)
    required_observations: list[str] = Field(default_factory=list)
    final_state_assertions: list[dict[str, Any]] = Field(min_length=1)
    gold_reason_tags: list[str] = Field(default_factory=list)
    authorized: bool
    source_refs: list[str] = Field(default_factory=list)
    author: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_gold_action_sets(self) -> Q5Gold:
        _require_unique(self.allowed_terminal_actions, field="allowed_terminal_actions")
        _require_unique(self.forbidden_terminal_actions, field="forbidden_terminal_actions")
        _require_unique(self.required_observations, field="required_observations")
        _require_unique(self.gold_reason_tags, field="gold_reason_tags")
        _require_unique(self.source_refs, field="source_refs")
        overlap = set(self.allowed_terminal_actions) & set(self.forbidden_terminal_actions)
        if overlap:
            raise ValueError(
                "allowed_terminal_actions and forbidden_terminal_actions overlap: "
                + ", ".join(sorted(overlap))
            )
        return self


def _require_unique(values: list[Any], *, field: str) -> None:
    normalized = [str(value) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")


Q5_TOOL_WHITELIST = frozenset(tool.value for tool in Q5ObservationTool)
Q5_GOLD_ONLY_FIELDS = frozenset(
    {
        "stratum",
        "gold_action",
        "gold_final_state",
        "gold_reason_tags",
        "allowed_terminal_actions",
        "forbidden_terminal_actions",
        "required_observations",
        "final_state_assertions",
        "authorized",
    }
)
