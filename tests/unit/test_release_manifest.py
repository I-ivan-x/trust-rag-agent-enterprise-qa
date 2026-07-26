from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.eval.release_manifest import (
    RELEASE_MANIFEST_PATH,
    RELEASE_SCHEMA_PATH,
    _verify_artifact,
    _verify_research_milestone,
    release_schema_bytes,
    verify_clean_clone_receipt_lineage,
    verify_release_manifest,
    verify_release_manifest_payload,
)
from app.schemas.release_manifest import (
    ReleaseArtifact,
    ReleaseCleanCloneReceipt,
    ReleaseManifest,
    ResearchMilestoneBinding,
)

ROOT = Path(__file__).resolve().parents[2]


def _manifest() -> ReleaseManifest:
    path = ROOT / RELEASE_MANIFEST_PATH
    if not path.is_file():
        pytest.skip("canonical release manifest is generated in the acceptance commit")
    return ReleaseManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _receipt(manifest: ReleaseManifest) -> ReleaseCleanCloneReceipt:
    return ReleaseCleanCloneReceipt.model_validate_json(
        (ROOT / manifest.clean_clone_receipt.path).read_text(encoding="utf-8")
    )


def test_release_schema_matches_strict_model() -> None:
    assert (ROOT / RELEASE_SCHEMA_PATH).read_bytes() == release_schema_bytes()


def test_canonical_release_manifest_verifies() -> None:
    manifest = _manifest()
    result = verify_release_manifest()
    assert result["tested_commit"] == manifest.tested_commit
    assert result["tested_tree"] == manifest.tested_tree
    assert result["stable_release"] == "v3.0-q4-reliability"
    assert (
        result["research_milestone"]
        == "agent-reliability-lab-q5-closed-20260717"
    )
    assert len(manifest.closure_documents) == 7
    assert result["model_requests"] == result["external_requests"] == 0
    assert result["q5_test"] == "absent"


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("missing_file", "docs/missing-q5-report.md"),
        ("wrong_hash", "0" * 64),
        ("wrong_commit", "0" * 40),
        ("wrong_tree", "f" * 40),
    ],
)
def test_release_manifest_mutations_fail_closed(mutation: str, value: str) -> None:
    payload = _manifest().model_dump(mode="json")
    if mutation == "missing_file":
        payload["reports"]["q5_final_report"]["path"] = value
    elif mutation == "wrong_hash":
        payload["reports"]["q5_final_report"]["sha256"] = value
    elif mutation == "wrong_commit":
        payload["tested_commit"] = value
    else:
        payload["tested_tree"] = value
    mutated = ReleaseManifest.model_validate(payload)
    with pytest.raises(ValueError):
        verify_release_manifest_payload(
            mutated,
            root=ROOT,
            require_current_tracking=True,
        )


def test_release_manifest_rejects_unknown_or_duplicate_structure() -> None:
    payload = _manifest().model_dump(mode="json")
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        ReleaseManifest.model_validate(payload)
    payload = _manifest().model_dump(mode="json")
    payload["frontend"]["screenshots"][1] = dict(payload["frontend"]["screenshots"][0])
    with pytest.raises(ValidationError):
        ReleaseManifest.model_validate(payload)


def test_ignored_or_untracked_dependency_fails(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("runtime/\n", encoding="utf-8")
    target = tmp_path / "runtime/dependency.json"
    target.parent.mkdir()
    target.write_text("{}\n", encoding="utf-8")
    raw = target.read_bytes()
    blob = hashlib.sha1(
        f"blob {len(raw)}\0".encode() + raw,
        usedforsecurity=False,
    ).hexdigest()
    artifact = ReleaseArtifact(
        path="runtime/dependency.json",
        sha256=hashlib.sha256(raw).hexdigest(),
        git_blob_sha=blob,
        size_bytes=len(raw),
    )
    with pytest.raises(ValueError, match="ignored or untracked"):
        _verify_artifact(
            tmp_path,
            artifact,
            None,
            require_current_tracking=True,
        )


def test_clean_clone_receipt_nonancestor_and_mismatch_fail() -> None:
    manifest = _manifest()
    payload = _receipt(manifest).model_dump(mode="json")
    payload["tested_commit"] = "0" * 40
    mutated = ReleaseCleanCloneReceipt.model_validate(payload)
    with pytest.raises(ValueError):
        verify_clean_clone_receipt_lineage(mutated, manifest, root=ROOT)


def test_research_milestone_requires_a_complete_annotated_tag(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    (tmp_path / "marker.txt").write_text("archive\n", encoding="utf-8")
    subprocess.run(["git", "add", "marker.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Archive Test",
            "-c",
            "user.email=archive@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "archive",
        ],
        cwd=tmp_path,
        check=True,
    )
    milestone = ResearchMilestoneBinding(
        name="agent-reliability-lab-q5-closed-20260717",
        status="scoped_negative_complete",
        tag_kind="annotated",
        target_policy="manifest-envelope-commit",
        release_created=False,
        stable_product_release_unchanged=True,
    )
    subprocess.run(["git", "tag", milestone.name], cwd=tmp_path, check=True)
    with pytest.raises(ValueError, match="annotated"):
        _verify_research_milestone(milestone, tmp_path)
    subprocess.run(["git", "tag", "--delete", milestone.name], cwd=tmp_path, check=True)
    message = (
        "scoped_negative_complete\n\n"
        "Open-world LLM value was not evaluated.\n"
        "v3.0-q4-reliability remains stable.\n"
        "This is not a product release.\n"
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Archive Test",
            "-c",
            "user.email=archive@example.invalid",
            "tag",
            "-a",
            milestone.name,
            "-m",
            message,
        ],
        cwd=tmp_path,
        check=True,
    )
    _verify_research_milestone(milestone, tmp_path)


def test_release_manifest_json_is_canonical() -> None:
    manifest = _manifest()
    expected = json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    assert (ROOT / RELEASE_MANIFEST_PATH).read_text(encoding="utf-8") == expected
