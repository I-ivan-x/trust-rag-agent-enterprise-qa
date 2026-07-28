"""Strict schemas for the reproducible public release evidence package."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
GIT_SHA_PATTERN = r"^[0-9a-f]{40}$"
REPOSITORY_PATH_PATTERN = r"^[^\\]+$"


class ReleaseArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, pattern=REPOSITORY_PATH_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    git_blob_sha: str = Field(pattern=GIT_SHA_PATTERN)
    size_bytes: int = Field(gt=0)

    @field_validator("path")
    @classmethod
    def _repository_relative_path(cls, value: str) -> str:
        parts = PurePosixPath(value).parts
        if not parts or value.startswith("/") or ":" in parts[0] or ".." in parts:
            raise ValueError("release artifact path must be repository relative")
        return value


class RuntimeVersions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operating_system: str = Field(min_length=1)
    architecture: str = Field(min_length=1)
    python: str = Field(min_length=1)
    uv: str = Field(min_length=1)
    node: str = Field(min_length=1)
    npm: str = Field(min_length=1)
    playwright: str = Field(min_length=1)
    chromium: str = Field(min_length=1)


class StableReleaseBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tag: Literal["v3.0-q4-reliability"]
    tag_kind: Literal["annotated"]
    tag_object_sha: str = Field(pattern=GIT_SHA_PATTERN)
    release_commit: str = Field(pattern=GIT_SHA_PATTERN)


class ResearchMilestoneBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["agent-reliability-lab-q5-closed-20260717"]
    status: Literal["scoped_negative_complete"]
    tag_kind: Literal["annotated"]
    tag_object_sha: str = Field(pattern=GIT_SHA_PATTERN)
    target_policy: Literal["immutable-archive-ancestor"]
    target_commit: str = Field(pattern=GIT_SHA_PATTERN)
    release_created: Literal[False]
    stable_product_release_unchanged: Literal[True]


class ClaimReleaseBindings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry: ReleaseArtifact
    presentation_catalog: ReleaseArtifact
    registry_schema: ReleaseArtifact
    generated_views: list[ReleaseArtifact] = Field(min_length=1)


class ReportReleaseBindings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    q5_final_report: ReleaseArtifact
    q5_claim_matrix: ReleaseArtifact
    boundary_summary: ReleaseArtifact


class BoundaryFReleaseBindings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_evidence: list[ReleaseArtifact] = Field(min_length=1)
    addendum_evidence: list[ReleaseArtifact] = Field(min_length=1)

    @model_validator(mode="after")
    def _layers_are_disjoint(self) -> BoundaryFReleaseBindings:
        original = {item.path for item in self.original_evidence}
        addendum = {item.path for item in self.addendum_evidence}
        if original & addendum:
            raise ValueError("Boundary F original and addendum evidence must be disjoint")
        return self


class FrontendReleaseBindings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    closure_receipt: ReleaseArtifact
    screenshots: list[ReleaseArtifact] = Field(min_length=3, max_length=3)


class ReleaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent-reliability-release-manifest-v2"]
    public_project_name: Literal["Agent Reliability Lab"]
    tested_commit: str = Field(pattern=GIT_SHA_PATTERN)
    tested_tree: str = Field(pattern=GIT_SHA_PATTERN)
    runtime_versions: RuntimeVersions
    python_lock: ReleaseArtifact
    frontend_lock: ReleaseArtifact
    release_schema: ReleaseArtifact
    claims: ClaimReleaseBindings
    reports: ReportReleaseBindings
    boundary_f: BoundaryFReleaseBindings
    showcase_manifest: ReleaseArtifact
    frontend: FrontendReleaseBindings
    clean_clone_receipt: ReleaseArtifact
    public_repository_audit: list[ReleaseArtifact] = Field(min_length=1)
    closure_documents: list[ReleaseArtifact] = Field(min_length=7, max_length=7)
    stable_release: StableReleaseBinding
    research_milestone: ResearchMilestoneBinding
    model_requests: Literal[0]
    external_requests: Literal[0]
    q5_test: Literal["absent"]

    @model_validator(mode="after")
    def _artifact_paths_are_unique_by_role(self) -> ReleaseManifest:
        screenshots = [item.path for item in self.frontend.screenshots]
        if len(screenshots) != len(set(screenshots)):
            raise ValueError("frontend screenshot paths must be unique")
        generated = [item.path for item in self.claims.generated_views]
        if len(generated) != len(set(generated)):
            raise ValueError("generated claim view paths must be unique")
        closure = [item.path for item in self.closure_documents]
        if len(closure) != len(set(closure)):
            raise ValueError("closure document paths must be unique")
        return self


class VerificationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    command: list[str] = Field(min_length=1)
    execution_launcher: Literal[
        "direct-executable",
        "uv-executable",
        "python-module-uv",
    ]
    working_directory: Literal["repository", "frontend"]
    environment: dict[str, str] = Field(min_length=3, max_length=3)
    status: Literal["passed"]

    @model_validator(mode="after")
    def _launcher_matches_logical_command(self) -> VerificationCommand:
        allowed = (
            {"uv-executable", "python-module-uv"}
            if self.command[0] == "uv"
            else {"direct-executable"}
        )
        if self.execution_launcher not in allowed:
            raise ValueError("execution launcher does not match logical command")
        return self


CLEAN_CLONE_ENVIRONMENT = {
    "UV_OFFLINE": "1",
    "npm_config_audit": "false",
    "npm_config_offline": "true",
}


def expected_clean_clone_commands(
    tested_commit: str,
) -> list[tuple[str, list[str], str, dict[str, str]]]:
    """Return the exact ordered command matrix bound into the clean-clone receipt."""

    python = ["uv", "run", "--frozen", "python"]
    root = "repository"
    frontend = "frontend"
    environment = CLEAN_CLONE_ENVIRONMENT
    return [
        (
            "uv_sync",
            ["uv", "sync", "--locked", "--group", "dev"],
            root,
            environment,
        ),
        ("claim_build", [*python, "scripts/build_public_claims.py"], root, environment),
        (
            "claim_check",
            [*python, "scripts/build_public_claims.py", "--check"],
            root,
            environment,
        ),
        (
            "claim_drift",
            [*python, "scripts/check_claim_drift.py"],
            root,
            environment,
        ),
        (
            "showcase_isolation",
            [*python, "scripts/build_interview_showcase.py", "--check"],
            root,
            environment,
        ),
        (
            "public_repository_audit",
            [*python, "scripts/verify_public_repository.py"],
            root,
            environment,
        ),
        (
            "release_gates",
            [
                *python,
                "scripts/check_release_gates.py",
                "--summary",
                "tests/fixtures/release_gates/ci_clean_summary.json",
                "--leakage",
                "tests/fixtures/release_gates/ci_clean_leakage.json",
            ],
            root,
            environment,
        ),
        ("npm_ci", ["npm", "ci"], frontend, environment),
        ("npm_build", ["npm", "run", "build"], frontend, environment),
        ("playwright", ["npx", "playwright", "test"], frontend, environment),
        (
            "frontend_receipt",
            [*python, "scripts/verify_frontend_closure.py"],
            root,
            environment,
        ),
        *[
            (
                f"lighthouse_{index}",
                [
                    "node",
                    "scripts/run-lighthouse.mjs",
                    tested_commit,
                    f"acceptance/runtime/release-clean-clone/run-{index}",
                ],
                frontend,
                environment,
            )
            for index in range(1, 4)
        ],
    ]


class LighthouseVerificationRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_index: int = Field(ge=1, le=3)
    performance: int = Field(ge=90, le=100)
    accessibility: int = Field(ge=90, le=100)
    external_requests: Literal[0]


class ReleaseCleanCloneReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent-reliability-clean-clone-receipt-v1"]
    tested_commit: str = Field(pattern=GIT_SHA_PATTERN)
    tested_tree: str = Field(pattern=GIT_SHA_PATTERN)
    clone_mode: Literal["git clone --no-hardlinks; detached checkout"]
    runtime_versions: RuntimeVersions
    commands: list[VerificationCommand] = Field(min_length=1)
    lighthouse_runs: list[LighthouseVerificationRun] = Field(min_length=3, max_length=3)
    claim_count: Literal[14]
    playwright_passed: int = Field(gt=0)
    playwright_skipped: int = Field(ge=0)
    release_gate_count: Literal[6]
    frontend_receipt_verified: Literal[True]
    screenshot_hashes_verified: Literal[True]
    clean_worktree_after_verification: Literal[True]
    ignored_or_untracked_dependency_count: Literal[0]
    model_requests: Literal[0]
    external_requests: Literal[0]
    request_observation_scope: Literal[
        "application counters and browser request capture; dependency installers "
        "forced offline; not an OS-level egress attestation"
    ]
    q5_test: Literal["absent"]
    status: Literal["passed"]

    @model_validator(mode="after")
    def _required_verification_matrix(self) -> ReleaseCleanCloneReceipt:
        actual = [
            (row.name, row.command, row.working_directory, row.environment)
            for row in self.commands
        ]
        expected = expected_clean_clone_commands(self.tested_commit)
        if actual != expected:
            raise ValueError("clean-clone command matrix changed, reordered, or substituted")
        if {row.run_index for row in self.lighthouse_runs} != {1, 2, 3}:
            raise ValueError("clean-clone Lighthouse run matrix must be exactly 1,2,3")
        return self
