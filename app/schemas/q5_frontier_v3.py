"""Closed contracts for the Q5 K0S semantic-frontier v3 namespace."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.q5_frontier import CanonicalPolicyIR, FrontierDisposition
from app.schemas.q5_frontier_v2 import (
    FrontierClauseSpan,
    FrontierTrustedObservation,
)


class FrontierRuntimePayloadV3(BaseModel):
    """Only payload available to the deterministic execution suite."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_ref: str = Field(pattern=r"^frontier-v3-resource:r[0-9]{3}$")
    policy_text: str = Field(min_length=1)
    query: str = Field(min_length=1)
    legal_dispositions: list[FrontierDisposition] = Field(min_length=1)
    trusted_observation: FrontierTrustedObservation

    @model_validator(mode="after")
    def _legal_surface(self) -> FrontierRuntimePayloadV3:
        if len(self.legal_dispositions) != len(set(self.legal_dispositions)):
            raise ValueError("legal dispositions must be unique")
        if FrontierDisposition.human_review not in self.legal_dispositions:
            raise ValueError("human_review must remain legal")
        return self


class FrontierOpenFieldProvenanceV3(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_path: Literal[
        "condition",
        "true_disposition",
        "false_disposition",
        "exceptions",
    ]
    policy_spans: list[FrontierClauseSpan] = Field(min_length=1)
    authorized_evidence_ids: list[str] = Field(min_length=1)


class FrontierClosedBindingV3(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_path: Literal[
        "scope.resource_type",
        "scope.allowed_scopes",
        "temporal_state",
        "precedence",
        "evidence_requirements.observation_type",
        "terminal_safety.allowed_dispositions",
    ]
    canonical_values: list[str] = Field(min_length=1)
    policy_spans: list[FrontierClauseSpan] = Field(min_length=1)


class FrontierSemanticCandidateV3(BaseModel):
    """Candidate Policy IR with provenance, not a semantic correctness receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-frontier-semantic-candidate-v3"] = (
        "q5-frontier-semantic-candidate-v3"
    )
    runtime_ref: str
    policy_ir: CanonicalPolicyIR
    closed_bindings: list[FrontierClosedBindingV3] = Field(min_length=6, max_length=6)
    open_provenance: list[FrontierOpenFieldProvenanceV3] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _field_closure(self) -> FrontierSemanticCandidateV3:
        closed = [item.field_path for item in self.closed_bindings]
        opened = [item.field_path for item in self.open_provenance]
        if len(closed) != len(set(closed)) or len(opened) != len(set(opened)):
            raise ValueError("semantic candidate provenance paths must be unique")
        return self


class FrontierAttestationV3(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-frontier-semantic-attestation-v3"] = (
        "q5-frontier-semantic-attestation-v3"
    )
    runtime_ref: str
    structural_integrity_verified: bool
    semantic_correctness_offline_graded: bool | None
    semantic_correctness_source: Literal["sealed_ir_offline_grader", "not_graded"]
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _semantic_source(self) -> FrontierAttestationV3:
        graded = self.semantic_correctness_offline_graded is not None
        if graded != (self.semantic_correctness_source == "sealed_ir_offline_grader"):
            raise ValueError("semantic correctness source is inconsistent")
        return self


class FrontierCompilerResultV3(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: FrontierDisposition
    scope_applicable: bool
    temporal_applicable: bool
    observation_type_matches: bool
    authorized: bool
    observation_completed: bool
    exception_matched: bool
    precedence_applied: Literal[
        "safety_guard",
        "ambiguity_guard",
        "base_only",
        "exception_overrides",
        "deny_overrides",
    ]


class FrontierExecutionRowV3(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-frontier-execution-row-v3"] = "q5-frontier-execution-row-v3"
    runtime_ref: str
    parser_status: Literal["complete", "abstain", "ambiguous", "unsafe"]
    parser_reason: str
    parser_suite: Literal["q5-deterministic-parser-suite-v3"]
    terminal_disposition: FrontierDisposition
    parsed_ir_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    llm_calls: Literal[0] = 0


class FrontierGradedRowV3(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-frontier-graded-row-v3"] = "q5-frontier-graded-row-v3"
    runtime_ref: str
    capability_class: Literal["symbolic_complete", "semantic_open", "ambiguous_or_unsafe"]
    policy_family: str
    semantic_phenomenon: str
    pair_id: str
    pair_kind: Literal["policy_fixed_state_changed", "state_fixed_policy_changed"]
    renderer_id: str
    renderer_distribution: Literal["preregistered", "held_out"]
    parser_status: str
    terminal_disposition: FrontierDisposition
    gold_disposition: FrontierDisposition
    success: bool
    unsafe_terminal: bool
    structural_integrity_verified: bool
    semantic_correctness_offline_graded: bool
    llm_calls: Literal[0] = 0
