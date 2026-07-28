"""Build and verify the versioned public release manifest."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.schemas.release_manifest import (
    BoundaryFReleaseBindings,
    ClaimReleaseBindings,
    FrontendReleaseBindings,
    ReleaseArtifact,
    ReleaseCleanCloneReceipt,
    ReleaseManifest,
    ReportReleaseBindings,
    ResearchMilestoneBinding,
    StableReleaseBinding,
)

ROOT = Path(__file__).resolve().parents[2]
RELEASE_ROOT = Path("data/releases")
RELEASE_SCHEMA_PATH = RELEASE_ROOT / "release_manifest_v2.schema.json"
RELEASE_MANIFEST_PATH = RELEASE_ROOT / "release_manifest_v2.json"
CLEAN_CLONE_RECEIPT_PATH = RELEASE_ROOT / "clean_clone_receipt_v1.json"
RESEARCH_MILESTONE_TAG = "agent-reliability-lab-q5-closed-20260717"

CLAIM_GENERATED_VIEWS = (
    "frontend/src/data/questions.json",
    "frontend/src/data/headline-results.json",
    "frontend/src/data/decision-frontier.json",
    "frontend/src/data/q5-evidence.json",
    "frontend/src/data/engineering-signals.json",
    "frontend/src/data/presentation-zh-cn.json",
)
BOUNDARY_F_ORIGINAL = (
    "data/q5_frontier/dev-k0u-audit/attack_metrics.json",
    "data/q5_frontier/dev-k0u-audit/audit_hashes.json",
    "data/q5_frontier/dev-k0u-audit/audit_report.md",
    "data/q5_frontier/dev-k0u-audit/audit_rows.jsonl",
    "data/q5_frontier/dev-k0u-audit/boundary_f_summary.json",
    "data/q5_frontier/dev-k0u-audit/k1_readiness.json",
    "data/q5_frontier/dev-k0u-audit/lineage_receipt.json",
    "data/q5_frontier/dev-k0u-audit/posthoc_complexity.json",
)
BOUNDARY_F_ADDENDUM = (
    "data/eval_runs/q5-boundary-f-addendum-z-a/addendum_metrics.json",
    "data/eval_runs/q5-boundary-f-addendum-z-a/addendum_report.md",
    "data/eval_runs/q5-boundary-f-addendum-z-a/addendum_rows.jsonl",
    "data/eval_runs/q5-boundary-f-addendum-z-a/artifact_hashes.json",
    "data/eval_runs/q5-boundary-f-addendum-z-a/frozen_scope.json",
    "data/eval_runs/q5-boundary-f-addendum-z-a/lineage_receipt.json",
    "data/eval_runs/q5-boundary-f-addendum-z-a/parser_attestation.json",
)
FRONTEND_SCREENSHOTS = (
    "frontend/acceptance/frontend-closure/desktop-1440x900.png",
    "frontend/acceptance/frontend-closure/laptop-1280x720.png",
    "frontend/acceptance/frontend-closure/mobile-390x844.png",
)
PUBLIC_AUDIT_ARTIFACTS = (
    ".gitleaks.toml",
    "data/public_repository/audit_registry_v1.json",
    "data/public_repository/audit_registry_v2.json",
    "data/public_repository/audit_registry_v2.schema.json",
    "data/public_repository/dependency_audit_v1.json",
    "docs/PUBLIC_REPOSITORY_AUDIT.md",
    "docs/DATA_PROVENANCE_AUDIT.md",
    "SECURITY.md",
)
CLOSURE_DOCUMENTS = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "LICENSES/FASTAPI-MIT.txt",
    "LICENSES/KUBERNETES-CC-BY-4.0.txt",
    "docs/THREE_MINUTE_DEMO_SCRIPT.md",
    "docs/RESUME_BULLETS.md",
    "docs/PROJECT_ARCHIVE_AND_MAINTENANCE.md",
)
REPORT_PATHS = {
    "q5_final_report": "docs/Q5_FINAL_REPORT.md",
    "q5_claim_matrix": "docs/Q5_CLAIM_MATRIX.md",
    "boundary_summary": "docs/Q5_BOUNDARY_A_F_SUMMARY.md",
}


def release_schema_bytes() -> bytes:
    payload = ReleaseManifest.model_json_schema()
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def write_release_schema(root: Path = ROOT) -> Path:
    target = root / RELEASE_SCHEMA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(release_schema_bytes())
    return target


def build_release_manifest(
    *,
    tested_commit: str,
    clean_clone_receipt: Path | str = CLEAN_CLONE_RECEIPT_PATH,
    root: Path = ROOT,
) -> ReleaseManifest:
    commit = _git(root, "rev-parse", f"{tested_commit}^{{commit}}")
    tree = _git(root, "rev-parse", f"{commit}^{{tree}}")
    receipt_path = _relative(root, Path(clean_clone_receipt))
    receipt = ReleaseCleanCloneReceipt.model_validate_json(
        (root / receipt_path).read_text(encoding="utf-8")
    )
    if receipt.tested_commit != commit or receipt.tested_tree != tree:
        raise ValueError("clean-clone receipt does not target the manifest commit/tree")

    manifest = ReleaseManifest(
        schema_version="agent-reliability-release-manifest-v2",
        public_project_name="Agent Reliability Lab",
        tested_commit=commit,
        tested_tree=tree,
        runtime_versions=receipt.runtime_versions,
        python_lock=_artifact(root, "uv.lock", commit),
        frontend_lock=_artifact(root, "frontend/package-lock.json", commit),
        release_schema=_artifact(root, RELEASE_SCHEMA_PATH.as_posix(), commit),
        claims=ClaimReleaseBindings(
            registry=_artifact(root, "data/claims/claim_registry.json", commit),
            presentation_catalog=_artifact(
                root, "data/claims/presentation_zh_cn_v1.json", commit
            ),
            registry_schema=_artifact(
                root, "data/claims/claim_registry.schema.json", commit
            ),
            generated_views=[
                _artifact(root, path, commit) for path in CLAIM_GENERATED_VIEWS
            ],
        ),
        reports=ReportReleaseBindings(
            **{
                field: _artifact(root, path, commit)
                for field, path in REPORT_PATHS.items()
            }
        ),
        boundary_f=BoundaryFReleaseBindings(
            original_evidence=[
                _artifact(root, path, commit) for path in BOUNDARY_F_ORIGINAL
            ],
            addendum_evidence=[
                _artifact(root, path, commit) for path in BOUNDARY_F_ADDENDUM
            ],
        ),
        showcase_manifest=_artifact(
            root, "data/showcase/interview-v1/manifest.json", commit
        ),
        frontend=FrontendReleaseBindings(
            closure_receipt=_artifact(
                root, "frontend/acceptance/frontend-closure/receipt.json", commit
            ),
            screenshots=[
                _artifact(root, path, commit) for path in FRONTEND_SCREENSHOTS
            ],
        ),
        clean_clone_receipt=_artifact(root, receipt_path, None),
        public_repository_audit=[
            _artifact(root, path, commit) for path in PUBLIC_AUDIT_ARTIFACTS
        ],
        closure_documents=[
            _artifact(root, path, commit) for path in CLOSURE_DOCUMENTS
        ],
        stable_release=_stable_release(root),
        research_milestone=ResearchMilestoneBinding(
            name=RESEARCH_MILESTONE_TAG,
            status="scoped_negative_complete",
            tag_kind="annotated",
            tag_object_sha=_research_milestone_tag_object(root),
            target_policy="immutable-archive-ancestor",
            target_commit=_research_milestone_target(root),
            release_created=False,
            stable_product_release_unchanged=True,
        ),
        model_requests=0,
        external_requests=0,
        q5_test="absent",
    )
    verify_release_manifest_payload(
        manifest,
        root=root,
        require_current_tracking=False,
    )
    return manifest


def write_release_manifest(
    *,
    tested_commit: str,
    clean_clone_receipt: Path | str = CLEAN_CLONE_RECEIPT_PATH,
    output: Path | str = RELEASE_MANIFEST_PATH,
    root: Path = ROOT,
) -> ReleaseManifest:
    manifest = build_release_manifest(
        tested_commit=tested_commit,
        clean_clone_receipt=clean_clone_receipt,
        root=root,
    )
    target = root / _relative(root, Path(output))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
    )
    return manifest


def verify_release_manifest(
    path: Path | str = RELEASE_MANIFEST_PATH,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    relative = _relative(root, Path(path))
    if not _tracked(root, relative):
        raise ValueError("release manifest must be Git tracked")
    manifest = ReleaseManifest.model_validate_json(
        (root / relative).read_text(encoding="utf-8")
    )
    verify_release_manifest_payload(manifest, root=root, require_current_tracking=True)
    return {
        "schema_version": manifest.schema_version,
        "manifest_path": relative,
        "manifest_sha256": _sha256(root / relative),
        "tested_commit": manifest.tested_commit,
        "tested_tree": manifest.tested_tree,
        "stable_release": manifest.stable_release.tag,
        "research_milestone": manifest.research_milestone.name,
        "model_requests": manifest.model_requests,
        "external_requests": manifest.external_requests,
        "q5_test": manifest.q5_test,
        "status": "passed",
    }


def verify_release_manifest_payload(
    manifest: ReleaseManifest,
    *,
    root: Path = ROOT,
    require_current_tracking: bool,
) -> None:
    actual_tree = _git(root, "rev-parse", f"{manifest.tested_commit}^{{tree}}")
    if actual_tree != manifest.tested_tree:
        raise ValueError("release manifest tested tree does not match tested commit")
    if not _is_ancestor(root, manifest.tested_commit, "HEAD"):
        raise ValueError("release manifest tested commit is not a current ancestor")
    if (root / "data/q5_test").exists():
        raise ValueError("q5_test must remain absent")
    _verify_research_milestone(
        manifest.research_milestone,
        root,
        tested_commit=manifest.tested_commit,
    )

    expected = _expected_paths()
    actual = _paths_by_role(manifest)
    if actual != expected:
        raise ValueError("release manifest artifact matrix is missing, extra, or reordered")

    receipt_path = manifest.clean_clone_receipt.path
    for artifact in _all_artifacts(manifest):
        tracked_in_tested_commit = artifact.path != receipt_path
        _verify_artifact(
            root,
            artifact,
            manifest.tested_commit if tracked_in_tested_commit else None,
            require_current_tracking=require_current_tracking,
        )
    if (root / RELEASE_SCHEMA_PATH).read_bytes() != release_schema_bytes():
        raise ValueError("release manifest JSON schema drifted from the Pydantic model")

    receipt = ReleaseCleanCloneReceipt.model_validate_json(
        (root / receipt_path).read_text(encoding="utf-8")
    )
    verify_clean_clone_receipt_lineage(receipt, manifest, root=root)
    _verify_frontend_receipt(manifest, root)
    _verify_showcase_manifest(root / manifest.showcase_manifest.path)
    stable_release = _stable_release(root)
    if stable_release != manifest.stable_release:
        raise ValueError("stable release binding changed")
    if not _is_ancestor(root, stable_release.release_commit, manifest.tested_commit):
        raise ValueError("stable release is not an ancestor of the tested commit")


def verify_clean_clone_receipt_lineage(
    receipt: ReleaseCleanCloneReceipt,
    manifest: ReleaseManifest,
    *,
    root: Path = ROOT,
) -> None:
    if (
        receipt.tested_commit != manifest.tested_commit
        or receipt.tested_tree != manifest.tested_tree
    ):
        raise ValueError("release clean-clone receipt commit/tree mismatch")
    if receipt.runtime_versions != manifest.runtime_versions:
        raise ValueError("release clean-clone receipt runtime versions mismatch")
    if not _is_ancestor(root, receipt.tested_commit, "HEAD"):
        raise ValueError("release clean-clone receipt points to a non-ancestor commit")


def _expected_paths() -> dict[str, tuple[str, ...]]:
    return {
        "locks": ("uv.lock", "frontend/package-lock.json"),
        "release_schema": (RELEASE_SCHEMA_PATH.as_posix(),),
        "claim_core": (
            "data/claims/claim_registry.json",
            "data/claims/presentation_zh_cn_v1.json",
            "data/claims/claim_registry.schema.json",
        ),
        "claim_views": CLAIM_GENERATED_VIEWS,
        "reports": tuple(REPORT_PATHS.values()),
        "boundary_f_original": BOUNDARY_F_ORIGINAL,
        "boundary_f_addendum": BOUNDARY_F_ADDENDUM,
        "showcase": ("data/showcase/interview-v1/manifest.json",),
        "frontend_receipt": ("frontend/acceptance/frontend-closure/receipt.json",),
        "frontend_screenshots": FRONTEND_SCREENSHOTS,
        "clean_clone_receipt": (CLEAN_CLONE_RECEIPT_PATH.as_posix(),),
        "public_repository_audit": PUBLIC_AUDIT_ARTIFACTS,
        "closure_documents": CLOSURE_DOCUMENTS,
    }


def _paths_by_role(manifest: ReleaseManifest) -> dict[str, tuple[str, ...]]:
    return {
        "locks": (manifest.python_lock.path, manifest.frontend_lock.path),
        "release_schema": (manifest.release_schema.path,),
        "claim_core": (
            manifest.claims.registry.path,
            manifest.claims.presentation_catalog.path,
            manifest.claims.registry_schema.path,
        ),
        "claim_views": tuple(item.path for item in manifest.claims.generated_views),
        "reports": (
            manifest.reports.q5_final_report.path,
            manifest.reports.q5_claim_matrix.path,
            manifest.reports.boundary_summary.path,
        ),
        "boundary_f_original": tuple(
            item.path for item in manifest.boundary_f.original_evidence
        ),
        "boundary_f_addendum": tuple(
            item.path for item in manifest.boundary_f.addendum_evidence
        ),
        "showcase": (manifest.showcase_manifest.path,),
        "frontend_receipt": (manifest.frontend.closure_receipt.path,),
        "frontend_screenshots": tuple(
            item.path for item in manifest.frontend.screenshots
        ),
        "clean_clone_receipt": (manifest.clean_clone_receipt.path,),
        "public_repository_audit": tuple(
            item.path for item in manifest.public_repository_audit
        ),
        "closure_documents": tuple(item.path for item in manifest.closure_documents),
    }


def _all_artifacts(manifest: ReleaseManifest) -> list[ReleaseArtifact]:
    return [
        manifest.python_lock,
        manifest.frontend_lock,
        manifest.release_schema,
        manifest.claims.registry,
        manifest.claims.presentation_catalog,
        manifest.claims.registry_schema,
        *manifest.claims.generated_views,
        manifest.reports.q5_final_report,
        manifest.reports.q5_claim_matrix,
        manifest.reports.boundary_summary,
        *manifest.boundary_f.original_evidence,
        *manifest.boundary_f.addendum_evidence,
        manifest.showcase_manifest,
        manifest.frontend.closure_receipt,
        *manifest.frontend.screenshots,
        manifest.clean_clone_receipt,
        *manifest.public_repository_audit,
        *manifest.closure_documents,
    ]


def _verify_research_milestone(
    milestone: ResearchMilestoneBinding,
    root: Path,
    *,
    tested_commit: str,
) -> None:
    if _git(root, "tag", "--list", "v4.0*"):
        raise ValueError("v4.0 product release must remain absent")
    if not _git(root, "tag", "--list", milestone.name):
        raise ValueError("research milestone tag is missing")
    reference = f"refs/tags/{milestone.name}"
    if _git(root, "cat-file", "-t", reference) != "tag":
        raise ValueError("research milestone must be an annotated tag")
    if _git(root, "rev-parse", reference) != milestone.tag_object_sha:
        raise ValueError("research milestone annotated tag object changed")
    target = _git(root, "rev-parse", f"{reference}^{{commit}}")
    if target != milestone.target_commit:
        raise ValueError("research milestone target differs from its recorded commit")
    if not _is_ancestor(root, target, tested_commit):
        raise ValueError("research milestone target is not an ancestor of the tested commit")
    message = _git(root, "for-each-ref", "--format=%(contents)", reference).lower()
    required = (
        "scoped_negative_complete",
        "open-world llm value was not evaluated",
        "v3.0-q4-reliability",
        "not a product release",
    )
    if any(token not in message for token in required):
        raise ValueError("research milestone annotation is incomplete")


def _research_milestone_target(root: Path) -> str:
    if not _git(root, "tag", "--list", RESEARCH_MILESTONE_TAG):
        raise ValueError("research milestone tag is missing")
    return _git(
        root,
        "rev-parse",
        f"refs/tags/{RESEARCH_MILESTONE_TAG}^{{commit}}",
    )


def _research_milestone_tag_object(root: Path) -> str:
    if not _git(root, "tag", "--list", RESEARCH_MILESTONE_TAG):
        raise ValueError("research milestone tag is missing")
    reference = f"refs/tags/{RESEARCH_MILESTONE_TAG}"
    if _git(root, "cat-file", "-t", reference) != "tag":
        raise ValueError("research milestone must be an annotated tag")
    return _git(root, "rev-parse", reference)


def _artifact(root: Path, path: str, tested_commit: str | None) -> ReleaseArtifact:
    target = root / path
    if not target.is_file():
        raise ValueError(f"release artifact is missing: {path}")
    if tested_commit is not None:
        blob = _blob_at(root, tested_commit, path)
        if _git_blob_sha(target.read_bytes()) != blob:
            raise ValueError(f"release artifact differs from tested commit: {path}")
    else:
        blob = _git_blob_sha(target.read_bytes())
    return ReleaseArtifact(
        path=path,
        sha256=_sha256(target),
        git_blob_sha=blob,
        size_bytes=target.stat().st_size,
    )


def _verify_artifact(
    root: Path,
    artifact: ReleaseArtifact,
    tested_commit: str | None,
    *,
    require_current_tracking: bool,
) -> None:
    target = root / artifact.path
    if not target.is_file():
        raise ValueError(f"release artifact is missing: {artifact.path}")
    if require_current_tracking and not _tracked(root, artifact.path):
        raise ValueError(f"release artifact is ignored or untracked: {artifact.path}")
    if _sha256(target) != artifact.sha256 or target.stat().st_size != artifact.size_bytes:
        raise ValueError(f"release artifact bytes changed: {artifact.path}")
    if _git_blob_sha(target.read_bytes()) != artifact.git_blob_sha:
        raise ValueError(f"release artifact Git blob changed: {artifact.path}")
    if (
        tested_commit is not None
        and _blob_at(root, tested_commit, artifact.path) != artifact.git_blob_sha
    ):
        raise ValueError(
            f"release artifact is absent or different in tested commit: {artifact.path}"
        )


def _verify_frontend_receipt(manifest: ReleaseManifest, root: Path) -> None:
    payload = json.loads(
        (root / manifest.frontend.closure_receipt.path).read_text(encoding="utf-8")
    )
    if payload.get("schema_version") != "frontend-closure-acceptance-v1":
        raise ValueError("unsupported frontend closure receipt")
    if payload.get("model_requests") != 0 or payload.get("external_requests") != 0:
        raise ValueError("frontend closure receipt contains requests")
    if not payload.get("hard_thresholds_passed"):
        raise ValueError("frontend closure hard thresholds did not pass")
    frontend_commit = str(payload.get("tested_commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", frontend_commit) or not _is_ancestor(
        root, frontend_commit, manifest.tested_commit
    ):
        raise ValueError("frontend receipt does not point to an ancestor implementation")
    frontend_tree = str(payload.get("tested_tree", ""))
    if (
        not re.fullmatch(r"[0-9a-f]{40}", frontend_tree)
        or _git(root, "rev-parse", f"{frontend_commit}^{{tree}}") != frontend_tree
    ):
        raise ValueError("frontend receipt tested tree does not match its commit")
    allowed_evidence_changes = {
        manifest.frontend.closure_receipt.path,
        *(item.path for item in manifest.frontend.screenshots),
    }
    changed_frontend_paths = {
        path
        for path in _git(
            root,
            "diff",
            "--name-only",
            f"{frontend_commit}..{manifest.tested_commit}",
            "--",
            "frontend",
        ).splitlines()
        if path
    }
    stale_inputs = changed_frontend_paths - allowed_evidence_changes
    if stale_inputs:
        raise ValueError(
            "frontend implementation changed after closure acceptance: "
            + ", ".join(sorted(stale_inputs))
        )
    recorded = {
        row["path"]: row["sha256"] for row in payload.get("screenshots", [])
    }
    expected = {item.path: item.sha256 for item in manifest.frontend.screenshots}
    if recorded != expected:
        raise ValueError("frontend screenshot hashes differ from the closure receipt")
    runs = payload.get("lighthouse_runs", [])
    if len(runs) != 3 or any(
        row.get("performance", 0) < 90
        or row.get("accessibility", 0) < 90
        or row.get("external_requests") != 0
        for row in runs
    ):
        raise ValueError("frontend closure Lighthouse matrix is invalid")


def _verify_showcase_manifest(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "data_mode": "synthetic",
        "use": "demonstration_only",
        "headline_eligible": False,
        "formal_evaluation": False,
        "model_requests": 0,
        "external_requests": 0,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("interview showcase publication boundary changed")


def _stable_release(root: Path) -> StableReleaseBinding:
    tag = "v3.0-q4-reliability"
    if _git(root, "cat-file", "-t", tag) != "tag":
        raise ValueError("stable release must remain an annotated tag")
    return StableReleaseBinding(
        tag=tag,
        tag_kind="annotated",
        tag_object_sha=_git(root, "rev-parse", tag),
        release_commit=_git(root, "rev-list", "-n", "1", tag),
    )


def _relative(root: Path, path: Path) -> str:
    candidate = path if path.is_absolute() else root / path
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("release artifact must be inside the repository") from exc


def _tracked(root: Path, path: str) -> bool:
    return (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    ) and (
        subprocess.run(
            ["git", "check-ignore", "--quiet", "--", path],
            cwd=root,
            capture_output=True,
        ).returncode
        != 0
    )


def _blob_at(root: Path, commit: str, path: str) -> str:
    output = _git(root, "ls-tree", commit, "--", path)
    if not output:
        raise ValueError(f"release artifact is not tracked at tested commit: {path}")
    fields = output.split(None, 3)
    if len(fields) < 4 or fields[1] != "blob":
        raise ValueError(f"release artifact is not a blob at tested commit: {path}")
    return fields[2]


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    )


def _git(root: Path, *args: str) -> str:
    return _run(["git", *args], root)


def _run(command: list[str], cwd: Path) -> str:
    executable = shutil.which(command[0])
    if executable:
        command = [executable, *command[1:]]
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"command failed ({' '.join(command)}): {details}")
    return completed.stdout.strip() or completed.stderr.strip()
