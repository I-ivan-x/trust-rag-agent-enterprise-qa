"""Canonical typed policy IR for the isolated Q5 capability frontier.

The models in this module are the only schema source for frontier authoring,
parsing, compilation, and artifact manifests. Runtime payloads deliberately do
not contain IR, grader labels, topology tags, or expected dispositions.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrontierDisposition(StrEnum):
    mark_stale = "mark_stale"
    remediate = "remediate"
    notify = "notify"
    human_review = "human_review"
    no_action = "no_action"


class FrontierPredicateField(StrEnum):
    status = "status"
    scope = "scope"
    temporal_state = "temporal_state"
    exception_active = "exception_active"


class FrontierPredicateOperator(StrEnum):
    eq = "eq"
    ne = "ne"
    in_set = "in"


class FrontierResourceType(StrEnum):
    incident = "incident"
    change = "change"
    access = "access"
    retention = "retention"


class FrontierTemporalState(StrEnum):
    current = "current"
    planned = "planned"
    completed = "completed"
    expired = "expired"


class FrontierPrecedence(StrEnum):
    exception_overrides = "exception_overrides"
    deny_overrides = "deny_overrides"
    base_only = "base_only"


class FrontierAmbiguityKind(StrEnum):
    none = "none"
    conflicting_clauses = "conflicting_clauses"
    underspecified_scope = "underspecified_scope"
    unsupported_construct = "unsupported_construct"


class FrontierPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: FrontierPredicateField
    operator: FrontierPredicateOperator
    value: str | bool | list[str]

    @model_validator(mode="after")
    def _validate_value_shape(self) -> FrontierPredicate:
        if self.operator == FrontierPredicateOperator.in_set:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("in predicate requires a non-empty value list")
            if len(self.value) != len(set(self.value)):
                raise ValueError("in predicate values must be unique")
        elif isinstance(self.value, list):
            raise ValueError("eq/ne predicate cannot use a list value")
        if self.field == FrontierPredicateField.exception_active and not isinstance(
            self.value, bool
        ):
            raise ValueError("exception_active predicates require a boolean")
        return self


class FrontierConditionExpression(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    all_of: list[FrontierPredicate] = Field(min_length=1)
    any_of: list[FrontierPredicate] = Field(default_factory=list)


class FrontierPolicyScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_type: FrontierResourceType
    allowed_scopes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_scopes(self) -> FrontierPolicyScope:
        if len(self.allowed_scopes) != len(set(self.allowed_scopes)):
            raise ValueError("allowed scopes must be unique")
        return self


class FrontierExceptionClause(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    predicate: FrontierPredicate
    disposition: FrontierDisposition


class FrontierEvidenceRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authorized_chunk_required: bool = True
    successful_observation_required: bool = True
    observation_type: Literal[
        "inspect_incident_state",
        "inspect_change_state",
        "inspect_access_scope",
        "inspect_retention_state",
    ]


class FrontierAmbiguityConflict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: FrontierAmbiguityKind = FrontierAmbiguityKind.none
    conflict_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _consistent_ambiguity(self) -> FrontierAmbiguityConflict:
        if (self.kind == FrontierAmbiguityKind.none) != (self.conflict_count == 0):
            raise ValueError("ambiguity kind and conflict count are inconsistent")
        return self


class FrontierTerminalSafetyConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_dispositions: list[FrontierDisposition] = Field(min_length=1)
    require_authorized_evidence: bool = True
    require_successful_observation: bool = True
    ambiguity_terminal: Literal["human_review"] = "human_review"
    unauthorized_terminal: Literal["human_review"] = "human_review"

    @model_validator(mode="after")
    def _unique_dispositions(self) -> FrontierTerminalSafetyConstraints:
        if len(self.allowed_dispositions) != len(set(self.allowed_dispositions)):
            raise ValueError("allowed dispositions must be unique")
        if FrontierDisposition.human_review not in self.allowed_dispositions:
            raise ValueError("human_review must remain a legal safe terminal")
        return self


class CanonicalPolicyIR(BaseModel):
    """Policy meaning, independent of case identity and rendered wording."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-canonical-policy-ir-v1"] = (
        "q5-canonical-policy-ir-v1"
    )
    scope: FrontierPolicyScope
    condition: FrontierConditionExpression
    temporal_state: FrontierTemporalState
    exceptions: list[FrontierExceptionClause] = Field(default_factory=list)
    precedence: FrontierPrecedence
    evidence_requirements: FrontierEvidenceRequirements
    true_disposition: FrontierDisposition
    false_disposition: FrontierDisposition
    ambiguity: FrontierAmbiguityConflict
    terminal_safety: FrontierTerminalSafetyConstraints

    @model_validator(mode="after")
    def _validate_terminal_surface(self) -> CanonicalPolicyIR:
        legal = set(self.terminal_safety.allowed_dispositions)
        emitted = {self.true_disposition, self.false_disposition} | {
            clause.disposition for clause in self.exceptions
        }
        if not emitted <= legal:
            raise ValueError("policy dispositions exceed terminal safety surface")
        return self


class FrontierEnvironmentState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_ref: str = Field(pattern=r"^frontier-resource:[a-z0-9-]+$")
    status: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    temporal_state: FrontierTemporalState
    exception_active: bool
    evidence_authorized: bool
    authorized_evidence_chunk_id: str = Field(pattern=r"^chunk:[a-z0-9-]+$")
    observation_successful: bool
    observation_request_id: str = Field(pattern=r"^observation:[a-z0-9-]+$")


class FrontierRuntimePayload(BaseModel):
    """The complete model/router-visible frontier payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_ref: str = Field(pattern=r"^frontier-resource:[a-z0-9-]+$")
    policy_text: str = Field(min_length=1)
    query: str = Field(min_length=1)
    legal_dispositions: list[FrontierDisposition] = Field(min_length=1)
    authorized_evidence_chunk_ids: list[str] = Field(min_length=1)
    trusted_observation: dict[str, str | bool]

    @model_validator(mode="after")
    def _runtime_closure(self) -> FrontierRuntimePayload:
        if len(self.legal_dispositions) != len(set(self.legal_dispositions)):
            raise ValueError("runtime legal dispositions must be unique")
        if len(self.authorized_evidence_chunk_ids) != len(
            set(self.authorized_evidence_chunk_ids)
        ):
            raise ValueError("runtime evidence ids must be unique")
        allowed_observation_fields = {
            "status",
            "scope",
            "temporal_state",
            "exception_active",
            "observation_successful",
            "observation_request_id",
        }
        if set(self.trusted_observation) != allowed_observation_fields:
            raise ValueError("trusted observation field closure mismatch")
        return self


class FrontierGold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_ref: str
    disposition: FrontierDisposition
    authorized: bool
    evidence_chunk_id: str
    observation_request_id: str
    compiler_schema: Literal["q5-frontier-gold-compiler-v1"] = (
        "q5-frontier-gold-compiler-v1"
    )


class FrontierTopologyRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_ref: str
    capability_class: Literal[
        "symbolic_complete", "semantic_open", "ambiguous_or_unsafe"
    ]
    policy_family: FrontierResourceType
    pair_id: str
    pair_kind: Literal["policy_fixed_state_changed", "state_fixed_policy_changed"]
    renderer_id: str


class FrontierParserResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["complete", "abstain", "ambiguous", "unsafe"]
    reason: Literal[
        "canonical_complete",
        "semantic_typed_complete",
        "incomplete_resolvable",
        "conflicting_clauses",
        "unsupported_construct",
        "unauthorized_evidence",
    ]
    parsed_ir: CanonicalPolicyIR | None = None

    @model_validator(mode="after")
    def _parsed_ir_only_when_complete(self) -> FrontierParserResult:
        if (self.status == "complete") != (self.parsed_ir is not None):
            raise ValueError("only complete parser results may carry typed IR")
        return self


class FrontierRouteFacts(BaseModel):
    """Router facts exclude identity, topology, Gold, and policy-family fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parser_status: Literal["complete", "abstain", "ambiguous", "unsafe"]
    parser_reason: str
    observation_successful: bool
    evidence_authorized: bool
    ambiguity_count: int = Field(ge=0)
    legal_dispositions: list[FrontierDisposition] = Field(min_length=1)


class FrontierRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Literal[
        "deterministic_parser_compiler", "llm_semantic_parser", "human_escalation"
    ]
    llm_allowed: bool
    terminal_disposition: FrontierDisposition | None = None


def compact_policy_ir_schema() -> dict[str, Any]:
    """Derive the canonical compact schema from Pydantic, never hand-maintained."""

    def strip_display_metadata(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: strip_display_metadata(item)
                for key, item in sorted(value.items())
                if key not in {"title", "default", "description", "examples"}
            }
        if isinstance(value, list):
            return [strip_display_metadata(item) for item in value]
        return value

    return strip_display_metadata(CanonicalPolicyIR.model_json_schema())
