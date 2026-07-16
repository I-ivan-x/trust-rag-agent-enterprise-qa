"""Strict runtime, execution, and grading contracts for Q5 Frontier K0R v2."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.q5_frontier import (
    CanonicalPolicyIR,
    FrontierDisposition,
)


class FrontierObservationType(StrEnum):
    inspect_incident_state = "inspect_incident_state"
    inspect_change_state = "inspect_change_state"
    inspect_access_scope = "inspect_access_scope"
    inspect_retention_state = "inspect_retention_state"


class FrontierObservationStatus(StrEnum):
    ok = "ok"
    not_found = "not_found"
    timeout = "timeout"
    error = "error"


class FrontierHostAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attestation_source: Literal["host_acl"] = "host_acl"
    authorized: bool
    authorized_evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _authorization_closure(self) -> FrontierHostAuthorization:
        if len(self.authorized_evidence_ids) != len(
            set(self.authorized_evidence_ids)
        ):
            raise ValueError("authorized evidence ids must be unique")
        if any(not item.startswith("chunk:") for item in self.authorized_evidence_ids):
            raise ValueError("authorized evidence ids require chunk: prefix")
        if not self.authorized and self.authorized_evidence_ids:
            raise ValueError("unauthorized observation cannot expose chunk ids")
        return self


class FrontierObservedState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    scope: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    temporal_state: Literal["current", "planned", "completed", "expired"]
    exception_active: bool


class FrontierTrustedObservation(BaseModel):
    """Closed host-attested observation passed to execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_type: FrontierObservationType
    status: FrontierObservationStatus
    success: bool
    authorization: FrontierHostAuthorization
    request_id: str = Field(pattern=r"^observation:[a-z0-9-]+$")
    state: FrontierObservedState | None

    @model_validator(mode="after")
    def _cross_field_consistency(self) -> FrontierTrustedObservation:
        completed = self.status in {
            FrontierObservationStatus.ok,
            FrontierObservationStatus.not_found,
        }
        if self.success != completed:
            raise ValueError("observation success disagrees with status")
        if self.success and self.state is None:
            raise ValueError("successful observation requires typed state")
        if not self.success and self.state is not None:
            raise ValueError("failed observation cannot expose state")
        if (
            self.success
            and self.authorization.authorized
            and not self.authorization.authorized_evidence_ids
        ):
            raise ValueError("authorized successful observation requires evidence")
        if not self.success and self.authorization.authorized_evidence_ids:
            raise ValueError("failed observation cannot authorize evidence")
        return self


class FrontierRuntimePayloadV2(BaseModel):
    """Entire execution-visible payload; no sealed labels or authoring state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_ref: str = Field(pattern=r"^frontier-v2-resource:r[0-9]{3}$")
    policy_text: str = Field(min_length=1)
    query: str = Field(min_length=1)
    legal_dispositions: list[FrontierDisposition] = Field(min_length=1)
    trusted_observation: FrontierTrustedObservation

    @model_validator(mode="after")
    def _legal_surface(self) -> FrontierRuntimePayloadV2:
        if len(self.legal_dispositions) != len(set(self.legal_dispositions)):
            raise ValueError("legal dispositions must be unique")
        if FrontierDisposition.human_review not in self.legal_dispositions:
            raise ValueError("human_review must remain legal")
        return self


class FrontierClauseSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _span_hash(self) -> FrontierClauseSpan:
        if self.end <= self.start:
            raise ValueError("policy span end must exceed start")
        if self.sha256 != hashlib.sha256(self.text.encode()).hexdigest():
            raise ValueError("policy span hash mismatch")
        return self


class FrontierFieldProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_path: str = Field(pattern=r"^[a-z][a-z0-9_.\[\]]+$")
    policy_spans: list[FrontierClauseSpan] = Field(min_length=1)
    authorized_evidence_ids: list[str] = Field(min_length=1)


class FrontierSemanticHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-frontier-semantic-handoff-v2"] = (
        "q5-frontier-semantic-handoff-v2"
    )
    policy_ir: CanonicalPolicyIR
    provenance: list[FrontierFieldProvenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_field_paths(self) -> FrontierSemanticHandoff:
        paths = [item.field_path for item in self.provenance]
        if len(paths) != len(set(paths)):
            raise ValueError("semantic provenance field paths must be unique")
        return self


class FrontierParserResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["complete", "abstain", "ambiguous", "unsafe"]
    reason: Literal[
        "structured_complete",
        "generic_clause_complete",
        "semantic_handoff_complete",
        "incomplete_resolvable",
        "conflicting_clauses",
        "unsupported_construct",
        "unsafe_authorization",
    ]
    ambiguity_count: int = Field(default=0, ge=0)
    policy_ir: CanonicalPolicyIR | None = None
    semantic_handoff: FrontierSemanticHandoff | None = None

    @model_validator(mode="after")
    def _parser_closure(self) -> FrontierParserResultV2:
        if (self.status == "complete") != (self.policy_ir is not None):
            raise ValueError("complete parser result requires policy IR")
        if (self.status == "ambiguous") != (self.ambiguity_count > 0):
            raise ValueError("ambiguity count must come from ambiguous parser result")
        if self.semantic_handoff and self.semantic_handoff.policy_ir != self.policy_ir:
            raise ValueError("semantic handoff and parser IR disagree")
        return self


class FrontierRouteFactsV2(BaseModel):
    """Construct only with derive_route_facts in the execution module."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parser_status: Literal["complete", "abstain", "ambiguous", "unsafe"]
    parser_reason: str
    parser_ambiguity_count: int = Field(ge=0)
    observation_successful: bool
    host_authorized: bool
    authorized_evidence_ids: list[str]
    legal_dispositions: list[FrontierDisposition]


class FrontierRouteDecisionV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Literal[
        "deterministic_parser_compiler",
        "llm_semantic_parser",
        "human_escalation",
    ]
    llm_allowed: bool
    safe_terminal: FrontierDisposition | None = None


class FrontierExecutionRowV2(BaseModel):
    """Label-free execution record produced without sealed inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-frontier-execution-row-v2"] = (
        "q5-frontier-execution-row-v2"
    )
    runtime_ref: str
    baseline: Literal[
        "structured_grammar_parser",
        "generic_clause_parser",
        "v4_symbolic_matcher_challenger",
        "escalate_all_control",
    ]
    parser_status: str
    parser_reason: str
    parser_ambiguity_count: int = Field(ge=0)
    route: str
    llm_allowed: bool
    llm_calls: Literal[0] = 0
    terminal_disposition: FrontierDisposition
    parsed_ir_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    semantic_handoff_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


class FrontierGradedBaselineRowV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-frontier-graded-baseline-row-v2"] = (
        "q5-frontier-graded-baseline-row-v2"
    )
    runtime_ref: str
    baseline: str
    capability_class: Literal[
        "symbolic_complete", "semantic_open", "ambiguous_or_unsafe"
    ]
    policy_family: str
    semantic_phenomenon: str
    pair_id: str
    pair_kind: Literal["policy_fixed_state_changed", "state_fixed_policy_changed"]
    parser_status: str
    route: str
    llm_calls: int = Field(ge=0)
    terminal_disposition: FrontierDisposition
    gold_disposition: FrontierDisposition
    success: bool
    unsafe_terminal: bool
