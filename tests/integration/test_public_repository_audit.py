from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.eval.public_repository_audit import (
    DEPENDENCY_AUDIT_PATH,
    REGISTRY_PATH,
    _tracked_paths,
    _verify_data_provenance_closure,
    _verify_dependency_audit,
    scan_sensitive_text,
    verify_formal_surface_text,
    verify_legacy_codename_path,
    verify_public_repository,
    verify_q5_test_absent,
)
from app.schemas.public_repository import (
    DependencyAudit,
    PublicRepositoryAuditRegistry,
)

ROOT = Path(__file__).resolve().parents[2]


def _registry() -> PublicRepositoryAuditRegistry:
    return PublicRepositoryAuditRegistry.model_validate_json(
        (ROOT / REGISTRY_PATH).read_text(encoding="utf-8")
    )


def _dependencies() -> DependencyAudit:
    return DependencyAudit.model_validate_json(
        (ROOT / DEPENDENCY_AUDIT_PATH).read_text(encoding="utf-8")
    )


def test_public_repository_audit_passes() -> None:
    result = verify_public_repository()
    assert result["status"] == "passed"
    assert result["secret_findings"] == result["pii_findings"] == 0
    assert result["showcase_formal_references"] == 0
    assert result["q5_test"] == "absent"
    assert result["model_requests"] == result["external_requests"] == 0


@pytest.mark.parametrize(
    "text",
    [
        "token=sk-abcdefghijklmnopqrstuvwxyz1234",
        "key=ghp_abcdefghijklmnopqrstuvwxyz123456",
        "-----BEGIN PRIVATE KEY-----",
        "https://admin:password@private.example/api",
        "customer@example.org",
        "13800138000",
        "service at 10.24.3.7",
    ],
)
def test_secret_or_pii_fixture_fails_on_public_path(text: str) -> None:
    assert scan_sensitive_text("docs/leak.md", text, ()) != []


def test_declared_synthetic_fixture_does_not_become_a_real_secret_finding() -> None:
    text = "fake canary sk-abcdefghijklmnopqrstuvwxyz1234 and alice@example.org"
    assert scan_sensitive_text("tests/fixtures/fake.txt", text, ("tests/",)) == []


def test_showcase_reference_in_formal_claim_fails() -> None:
    with pytest.raises(ValueError, match="showcase corpus leaked"):
        verify_formal_surface_text(
            "data/claims/claim_registry.json",
            '{"source_path":"data/showcase/interview-v1/manifest.json"}',
        )


def test_legacy_codename_outside_allowlist_fails() -> None:
    with pytest.raises(ValueError, match="outside the allowlist"):
        verify_legacy_codename_path(
            "docs/new-marketing-page.md",
            "TrustRAG is the current product.",
            _registry(),
        )


def test_q5_test_tracked_mutation_fails_without_creating_the_split() -> None:
    with pytest.raises(ValueError, match="q5_test"):
        verify_q5_test_absent(ROOT, {"data/q5_test/tasks.jsonl"})


def test_missing_data_root_declaration_fails() -> None:
    registry = _registry()
    payload = registry.model_dump(mode="json")
    payload["data_roots"] = payload["data_roots"][1:]
    mutated = PublicRepositoryAuditRegistry.model_validate(payload)
    with pytest.raises(ValueError, match="root closure"):
        _verify_data_provenance_closure(mutated, ROOT, _tracked_paths(ROOT))


def test_public_third_party_without_license_status_fails() -> None:
    payload = _registry().model_dump(mode="json")
    row = next(
        item
        for item in payload["data_roots"]
        if "public-third-party" in item["source_types"]
    )
    row["redistribution_status"] = "project-owned"
    with pytest.raises(ValidationError):
        PublicRepositoryAuditRegistry.model_validate(payload)


@pytest.mark.parametrize("field", ["uv_lock_sha256", "package_lock_sha256"])
def test_dependency_lock_mutation_fails(field: str) -> None:
    payload = _dependencies().model_dump(mode="json")
    payload[field] = "0" * 64
    with pytest.raises(ValueError, match="hash drifted"):
        _verify_dependency_audit(DependencyAudit.model_validate(payload), ROOT)


def test_dependency_inventory_missing_row_fails() -> None:
    payload = _dependencies().model_dump(mode="json")
    payload["python"].pop()
    with pytest.raises(ValueError, match="inventory"):
        _verify_dependency_audit(DependencyAudit.model_validate(payload), ROOT)


def test_registry_json_is_canonical_json() -> None:
    registry = _registry()
    expected = json.dumps(registry.model_dump(mode="json"), indent=2) + "\n"
    actual = (ROOT / REGISTRY_PATH).read_text(encoding="utf-8")
    assert json.loads(actual) == json.loads(expected)
