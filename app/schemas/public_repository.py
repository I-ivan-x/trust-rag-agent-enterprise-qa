"""Strict schemas for the public-repository and data-provenance audit."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataSourceType(StrEnum):
    project_authored = "project-authored"
    synthetic = "synthetic"
    public_third_party = "public-third-party"
    historical_immutable_artifact = "historical-immutable-artifact"


class RedistributionStatus(StrEnum):
    project_owned = "project-owned"
    synthetic_project_owned = "synthetic-project-owned"
    upstream_license_with_attribution = "upstream-license-with-attribution"
    canonical_evidence_byte_frozen = "canonical-evidence-byte-frozen"


class DataRootAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root: str = Field(pattern=r"^data/[a-z0-9_]+/$")
    source_types: list[DataSourceType] = Field(min_length=1)
    redistribution_status: RedistributionStatus
    license_status: str = Field(min_length=1)
    provenance_evidence: list[str] = Field(min_length=1)
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def _third_party_license_is_explicit(self) -> DataRootAudit:
        if (
            DataSourceType.public_third_party in self.source_types
            and self.redistribution_status
            is not RedistributionStatus.upstream_license_with_attribution
        ):
            raise ValueError("public third-party data requires upstream license attribution")
        return self


class LegacyCodenamePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    codename: Literal["TrustRAG"]
    allowed_path_prefixes: list[str] = Field(min_length=1)
    allowed_exact_paths: list[str] = Field(min_length=1)
    current_public_identity: Literal["Agent Reliability Lab"]


class RepositoryLicenseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["selected"]
    spdx_identifier: Literal["Apache-2.0"]
    license_file_created: Literal[True]
    license_path: Literal["LICENSE"]
    license_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    third_party_notices_path: Literal["THIRD_PARTY_NOTICES.md"]
    third_party_notices_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    applies_to: list[str] = Field(min_length=1)
    excludes: list[str] = Field(min_length=1)


class ThirdPartyMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    path_prefixes: list[str] = Field(min_length=1)
    spdx_identifier: Literal["MIT", "CC-BY-4.0"]
    copyright_notice: str = Field(min_length=1)
    source_repository: str = Field(pattern=r"^https://github\.com/")
    exact_upstream_commit: str = Field(pattern=r"^(unknown|[0-9a-f]{40})$")
    license_copy_path: Literal[
        "LICENSES/FASTAPI-MIT.txt",
        "LICENSES/KUBERNETES-CC-BY-4.0.txt",
    ]
    license_copy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    modification_status: str = Field(min_length=1)
    canonical_evidence_policy: Literal[
        "byte-frozen-in-this-repository; downstream modification remains permitted "
        "under the applicable upstream license but is no longer canonical evidence"
    ]


class PublicRepositoryAuditRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["public-repository-audit-v2"]
    public_project_name: Literal["Agent Reliability Lab"]
    public_subtitle: Literal[
        "Governed Runtime, Evaluation Harness, and Decision Frontier for Tool-Using Agents"
    ]
    frontend_package_name: Literal["agent-reliability-lab-showcase"]
    legacy_python_distribution_name: Literal["trust-rag-agent-enterprise-qa"]
    stable_release: Literal["v3.0-q4-reliability"]
    data_roots: list[DataRootAudit] = Field(min_length=1)
    legacy_codename_policy: LegacyCodenamePolicy
    repository_license: RepositoryLicenseDecision
    third_party_materials: list[ThirdPartyMaterial] = Field(min_length=2, max_length=2)
    secret_fixture_path_prefixes: list[str]
    tracked_ignored_exceptions: list[str]
    public_brand_surfaces: list[str] = Field(min_length=1)
    formal_claim_surfaces: list[str] = Field(min_length=1)
    q5_test: Literal["absent"]
    model_requests: Literal[0]
    external_requests: Literal[0]

    @model_validator(mode="after")
    def _data_roots_are_unique(self) -> PublicRepositoryAuditRegistry:
        roots = [row.root for row in self.data_roots]
        if len(roots) != len(set(roots)):
            raise ValueError("data provenance roots must be unique")
        return self


class DependencyLicenseRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package: str = Field(min_length=1)
    scope: Literal["runtime", "optional", "development"]
    license: str = Field(min_length=1)
    status: Literal["compatible-review", "tooling-only"]


class DependencyAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["public-dependency-audit-v1"]
    uv_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    python: list[DependencyLicenseRow] = Field(min_length=1)
    npm: list[DependencyLicenseRow] = Field(min_length=1)
    python_advisory_status: Literal["offline-review-no-known-direct-runtime-advisory"]
    npm_production_vulnerabilities: Literal[0]
    npm_high_vulnerabilities: Literal[0]
    npm_critical_vulnerabilities: Literal[0]
    npm_moderate_vulnerabilities: Literal[0]
    accepted_moderate_advisory: Literal["none"]
    accepted_advisory_scope: Literal["none"]
    breaking_downgrade_performed: Literal[False]
    external_requests: Literal[0]
