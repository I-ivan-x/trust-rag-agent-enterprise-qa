"""Strict schema for the canonical public claim registry."""

from __future__ import annotations

import math
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClaimStatus(StrEnum):
    demonstrated_in_frozen_scope = "demonstrated_in_frozen_scope"
    falsified_in_current_scope = "falsified_in_current_scope"
    not_evaluated = "not_evaluated"


class EvidenceMode(StrEnum):
    real = "real"
    mock = "mock"
    synthetic = "synthetic"
    replay = "replay"
    offline_control = "offline_control"


class ClaimMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    numerator: float
    denominator: float = Field(gt=0)
    value: float
    unit: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def _value_matches_fraction(self) -> ClaimMetric:
        expected = self.numerator / self.denominator
        if not math.isclose(self.value, expected, rel_tol=0, abs_tol=0.00005):
            raise ValueError("claim metric value must match numerator / denominator")
        return self


class ClaimSourceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, pattern=r"^[^\\]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    evidence_commit: str = Field(pattern=r"^[0-9a-f]{40}$")

    @field_validator("path")
    @classmethod
    def _repository_relative_path(cls, value: str) -> str:
        parts = PurePosixPath(value).parts
        if value.startswith("/") or ":" in parts[0] or ".." in parts:
            raise ValueError("claim source path must be repository relative")
        return value


class PublicClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(pattern=r"^q[1-5]\.[a-z][a-z0-9_]*$")
    question_id: Literal["Q1", "Q2", "Q3", "Q4", "Q5"]
    public_label: str = Field(min_length=1)
    status: ClaimStatus
    claim_scope: str = Field(min_length=1)
    evidence_mode: EvidenceMode
    split_or_frozen_scope: str = Field(min_length=1)
    source_artifacts: list[ClaimSourceArtifact] = Field(min_length=1)
    metrics: dict[str, ClaimMetric]
    headline_eligible: bool
    limitations: list[str] = Field(min_length=1)
    public_summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _evaluation_semantics(self) -> PublicClaim:
        if self.status is ClaimStatus.not_evaluated and self.metrics:
            raise ValueError("not_evaluated claims must not fabricate metrics")
        if self.status is not ClaimStatus.not_evaluated and not self.metrics:
            raise ValueError("evaluated claims require at least one structured metric")
        if "proven" in self.public_summary.lower() or "proven" in self.public_label.lower():
            raise ValueError("public claims must use scoped demonstration language, not proven")
        return self


class ClaimRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["public-claim-registry-v1"]
    project_public_name: Literal["Agent Reliability Lab"]
    legacy_codename: Literal["TrustRAG"]
    q5_overall_status: Literal["scoped_negative_complete"]
    claims: list[PublicClaim] = Field(min_length=1)

    @model_validator(mode="after")
    def _registry_invariants(self) -> ClaimRegistry:
        ids = [claim.claim_id for claim in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim IDs must be unique")
        if {claim.question_id for claim in self.claims} != {"Q1", "Q2", "Q3", "Q4", "Q5"}:
            raise ValueError("claim registry must cover Q1-Q5")
        required_q5 = {
            "q5.selective_runtime_architecture": ClaimStatus.demonstrated_in_frozen_scope,
            "q5.observation_adaptation": ClaimStatus.demonstrated_in_frozen_scope,
            "q5.schema_transition_safety": ClaimStatus.demonstrated_in_frozen_scope,
            "q5.hybrid_efficiency": ClaimStatus.demonstrated_in_frozen_scope,
            "q5.llm_semantic_uplift": ClaimStatus.falsified_in_current_scope,
            "q5.controlled_prose_llm_necessity": ClaimStatus.falsified_in_current_scope,
            "q5.open_world_llm_value": ClaimStatus.not_evaluated,
        }
        by_id = {claim.claim_id: claim for claim in self.claims}
        if not required_q5.keys() <= by_id.keys():
            raise ValueError("Q5 claim matrix is incomplete")
        if any(by_id[claim_id].status is not status for claim_id, status in required_q5.items()):
            raise ValueError("Q5 claim status matrix changed")
        hybrid = by_id["q5.hybrid_efficiency"]
        if (
            hybrid.evidence_mode is not EvidenceMode.real
            or hybrid.split_or_frozen_scope != "real-dev"
        ):
            raise ValueError("Q5 hybrid efficiency must remain scoped to real-dev evidence")
        controlled = by_id["q5.controlled_prose_llm_necessity"]
        if "frozen controlled-prose" not in controlled.split_or_frozen_scope:
            raise ValueError("controlled-prose claim must name its frozen scope")
        return self
