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


class MetricDerivation(StrEnum):
    direct = "direct"
    ratio = "ratio"
    rate_from_value = "rate_from_value"
    difference = "difference"
    boolean = "boolean"


class ClaimMetricSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_path: str = Field(min_length=1, pattern=r"^[^\\]+$")
    derivation: MetricDerivation
    numerator_pointer: str | None = None
    denominator_pointer: str | None = None
    value_pointer: str | None = None
    left_pointer: str | None = None
    right_pointer: str | None = None
    tolerance: float = Field(gt=0, le=0.01)

    @field_validator("source_path")
    @classmethod
    def _source_path_is_repository_relative(cls, value: str) -> str:
        return _repository_relative_path(value)

    @field_validator(
        "numerator_pointer",
        "denominator_pointer",
        "value_pointer",
        "left_pointer",
        "right_pointer",
    )
    @classmethod
    def _json_pointer(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("/"):
            raise ValueError("metric source pointers must be JSON pointers")
        return value

    @model_validator(mode="after")
    def _derivation_contract(self) -> ClaimMetricSource:
        required = {
            MetricDerivation.direct: {"value_pointer"},
            MetricDerivation.ratio: {"numerator_pointer", "denominator_pointer"},
            MetricDerivation.rate_from_value: {"value_pointer", "denominator_pointer"},
            MetricDerivation.difference: {
                "left_pointer",
                "right_pointer",
                "denominator_pointer",
            },
            MetricDerivation.boolean: {"value_pointer"},
        }[self.derivation]
        present = {
            name
            for name in (
                "numerator_pointer",
                "denominator_pointer",
                "value_pointer",
                "left_pointer",
                "right_pointer",
            )
            if getattr(self, name) is not None
        }
        optional = {"value_pointer"} if self.derivation in {
            MetricDerivation.ratio,
            MetricDerivation.difference,
        } else set()
        if not required <= present or not present <= required | optional:
            raise ValueError(f"invalid pointer set for {self.derivation.value} derivation")
        return self


class ClaimMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    numerator: float
    denominator: float = Field(gt=0)
    value: float
    unit: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    source: ClaimMetricSource

    @model_validator(mode="after")
    def _value_matches_fraction(self) -> ClaimMetric:
        expected = self.numerator / self.denominator
        if not math.isclose(self.value, expected, rel_tol=0, abs_tol=0.00005):
            raise ValueError("claim metric value must match numerator / denominator")
        return self


class ClaimSourceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, pattern=r"^[^\\]+$")
    archived_from_path: str = Field(min_length=1, pattern=r"^[^\\]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    execution_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifact_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    release_tag: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    tag_object_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    release_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")

    @field_validator("path", "archived_from_path")
    @classmethod
    def _repository_relative_path(cls, value: str) -> str:
        return _repository_relative_path(value)

    @model_validator(mode="after")
    def _tag_fields_are_complete(self) -> ClaimSourceArtifact:
        tag_fields = (self.release_tag, self.tag_object_sha, self.release_commit)
        if any(tag_fields) and not all(tag_fields):
            raise ValueError("release tag, tag object SHA, and release commit move together")
        return self


class SourceSafetyAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    secret_scan: Literal["clear"]
    personal_data_scan: Literal["clear"]
    prompt_text_review: Literal["none", "hash_and_version_only"]
    publication_boundary: str = Field(min_length=1)
    license_and_data_boundary: str = Field(min_length=1)


class SourceImportAuditRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_path: str = Field(min_length=1, pattern=r"^data/claims/source/[^\\]+$")
    archived_from_path: str = Field(min_length=1, pattern=r"^data/eval_runs/[^\\]+$")
    original_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    execution_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifact_import_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    size_bytes: int = Field(gt=0)
    safety: SourceSafetyAudit

    @field_validator("source_path", "archived_from_path")
    @classmethod
    def _paths_are_repository_relative(cls, value: str) -> str:
        return _repository_relative_path(value)


class SourceImportAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["public-claim-source-import-v1"]
    artifacts: list[SourceImportAuditRow] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_sources(self) -> SourceImportAudit:
        paths = [row.source_path for row in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("source import audit paths must be unique")
        return self


class CleanCloneVerificationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["public-claim-clean-clone-receipt-v1"]
    tested_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    tested_tree: str = Field(pattern=r"^[0-9a-f]{40}$")
    claim_count: Literal[14]
    raw_source_count: int = Field(gt=0)
    source_blob_count: int = Field(gt=0)
    generated_file_count: int = Field(gt=0)
    ignored_file_dependency_count: Literal[0]
    schema_check: Literal["passed"]
    source_lineage_check: Literal["passed"]
    generator_check: Literal["passed"]


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


class ZhCnClaimPresentation(BaseModel):
    """Chinese presentation templates; canonical metrics remain the only number source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1)
    claim_scope_template: str = Field(min_length=1)
    frozen_scope_template: str = Field(min_length=1)
    limitations_templates: list[str] = Field(min_length=1)
    summary_template: str = Field(min_length=1)
    meaning_template: str = Field(min_length=1)


class ZhCnDecisionFrontierSegmentPresentation(BaseModel):
    """Chinese copy for one generated Q5 decision-frontier segment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1)
    route: str = Field(min_length=1)
    parser_status: str = Field(min_length=1)
    llm_called: str = Field(min_length=1)
    terminal_outcome: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    final_decision: str = Field(min_length=1)


class ZhCnPresentationCatalog(BaseModel):
    """Versioned localization SSOT consumed by the public-claim generator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["public-claim-presentation-zh-cn-v1"]
    locale: Literal["zh-CN"]
    question_labels: dict[str, str]
    status_labels: dict[str, str]
    evidence_mode_labels: dict[str, str]
    derivation_labels: dict[str, str]
    metric_labels: dict[str, str]
    decision_frontier_segments: dict[
        str, ZhCnDecisionFrontierSegmentPresentation
    ]
    claims: dict[str, ZhCnClaimPresentation]

    @model_validator(mode="after")
    def _nonempty_catalog_values(self) -> ZhCnPresentationCatalog:
        collections = (
            self.question_labels,
            self.status_labels,
            self.evidence_mode_labels,
            self.derivation_labels,
            self.metric_labels,
        )
        if any(
            not values or any(not value.strip() for value in values.values())
            for values in collections
        ):
            raise ValueError("presentation catalog mappings must be non-empty")
        return self


class ClaimRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["public-claim-registry-v2"]
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


def _repository_relative_path(value: str) -> str:
    parts = PurePosixPath(value).parts
    if not parts or value.startswith("/") or ":" in parts[0] or ".." in parts:
        raise ValueError("claim source path must be repository relative")
    return value
