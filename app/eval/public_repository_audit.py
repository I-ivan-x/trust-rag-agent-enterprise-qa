"""Fail-closed audit for publishing the repository and its tracked data."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from app.eval.showcase_corpus import verify_interview_showcase
from app.schemas.public_repository import (
    DataSourceType,
    DependencyAudit,
    PublicRepositoryAuditRegistry,
    RepositoryLicenseDecision,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path("data/public_repository/audit_registry_v2.json")
DEPENDENCY_AUDIT_PATH = Path("data/public_repository/dependency_audit_v1.json")
REGISTRY_SCHEMA_PATH = Path("data/public_repository/audit_registry_v2.schema.json")
IGNORED_GENERATED_PREFIXES = (
    "data/generated/",
    "data/indexes/",
    "frontend/dist/",
    "frontend/acceptance/runtime/",
)
SECRET_PATTERNS = {
    "private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE
    ),
    "openai_token": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "credential_url": re.compile(r"https?://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
}
PII_PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "us_ssn": re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
    "cn_mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "private_ipv4": re.compile(
        r"(?<![\d.])(?:10\.(?:\d{1,3}\.){2}\d{1,3}|"
        r"192\.168\.(?:\d{1,3}\.)\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})(?![\d.])"
    ),
}


def verify_public_repository(
    root: Path = ROOT,
    *,
    require_tracked_registry: bool = True,
) -> dict:
    registry_path = root / REGISTRY_PATH
    dependency_path = root / DEPENDENCY_AUDIT_PATH
    if require_tracked_registry and (
        not _tracked(root, REGISTRY_PATH.as_posix())
        or not _tracked(root, DEPENDENCY_AUDIT_PATH.as_posix())
    ):
        raise ValueError("public repository audit inputs must be Git tracked")
    registry = PublicRepositoryAuditRegistry.model_validate_json(
        registry_path.read_text(encoding="utf-8")
    )
    dependencies = DependencyAudit.model_validate_json(
        dependency_path.read_text(encoding="utf-8")
    )
    schema_path = root / REGISTRY_SCHEMA_PATH
    if (
        not schema_path.is_file()
        or (require_tracked_registry and not _tracked(root, REGISTRY_SCHEMA_PATH.as_posix()))
        or schema_path.read_bytes() != public_registry_schema_bytes()
    ):
        raise ValueError("public repository audit registry schema drifted")
    tracked = _tracked_paths(root)
    verify_q5_test_absent(root, tracked)
    _verify_data_provenance_closure(registry, root, tracked)
    _verify_repository_license(registry.repository_license, root, tracked)
    _verify_third_party_materials(registry, root, tracked)
    _verify_dependency_audit(dependencies, root)
    _verify_tracked_ignored_boundary(registry, root, tracked)
    _verify_showcase_claim_isolation(registry, root)
    _verify_legacy_codename(registry, root, tracked)
    _verify_public_brand(registry, root)
    findings = _scan_repository_text(registry, root, tracked)
    verify_interview_showcase(
        root / "data/showcase/interview-v1",
        verify_formal_isolation=True,
    )
    return {
        "schema_version": registry.schema_version,
        "tracked_file_count": len(tracked),
        "data_root_count": len(registry.data_roots),
        "secret_findings": findings["secret_findings"],
        "pii_findings": findings["pii_findings"],
        "ignored_tracked_file_count": 0,
        "showcase_formal_references": 0,
        "legacy_codename_violations": 0,
        "repository_license_status": registry.repository_license.status,
        "repository_license": registry.repository_license.spdx_identifier,
        "license_sha256": registry.repository_license.license_sha256,
        "third_party_notices_sha256": (
            registry.repository_license.third_party_notices_sha256
        ),
        "model_requests": registry.model_requests,
        "external_requests": registry.external_requests,
        "q5_test": registry.q5_test,
        "status": "passed",
    }


def public_registry_schema_bytes() -> bytes:
    return (
        json.dumps(
            PublicRepositoryAuditRegistry.model_json_schema(),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def write_public_registry_schema(root: Path = ROOT) -> Path:
    target = root / REGISTRY_SCHEMA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(public_registry_schema_bytes())
    return target


def verify_q5_test_absent(root: Path, tracked: Iterable[str] = ()) -> None:
    if (root / "data/q5_test").exists() or any(
        path == "data/q5_test" or path.startswith("data/q5_test/") for path in tracked
    ):
        raise ValueError("q5_test must remain absent")


def scan_sensitive_text(
    path: str,
    text: str,
    fixture_prefixes: Iterable[str],
) -> list[str]:
    fixture = any(path.startswith(prefix) for prefix in fixture_prefixes)
    findings = [
        f"secret:{name}"
        for name, pattern in SECRET_PATTERNS.items()
        if pattern.search(text)
    ]
    pii = [
        f"pii:{name}"
        for name, pattern in PII_PATTERNS.items()
        if pattern.search(text)
        and path not in {"uv.lock", "frontend/package-lock.json"}
    ]
    if fixture:
        return []
    return findings + pii


def verify_legacy_codename_path(
    path: str,
    text: str,
    registry: PublicRepositoryAuditRegistry,
) -> None:
    if not re.search(r"TrustRAG|trust-rag|trust_rag|trustrag", text, re.IGNORECASE):
        return
    policy = registry.legacy_codename_policy
    allowed = path in policy.allowed_exact_paths or any(
        path.startswith(prefix) for prefix in policy.allowed_path_prefixes
    )
    if not allowed:
        raise ValueError(f"legacy codename appears outside the allowlist: {path}")


def verify_formal_surface_text(path: str, text: str) -> None:
    normalized = text.replace("\\", "/").lower()
    if "data/showcase/" in normalized or "interview-v1" in normalized:
        raise ValueError(f"showcase corpus leaked into formal claim surface: {path}")


def _verify_data_provenance_closure(
    registry: PublicRepositoryAuditRegistry,
    root: Path,
    tracked: set[str],
) -> None:
    actual_roots = {
        f"data/{PurePosixPath(path).parts[1]}/"
        for path in tracked
        if path.startswith("data/") and len(PurePosixPath(path).parts) > 2
    }
    declared = {row.root for row in registry.data_roots}
    if actual_roots != declared:
        missing = sorted(actual_roots - declared)
        extra = sorted(declared - actual_roots)
        raise ValueError(f"data provenance root closure failed: missing={missing}, extra={extra}")
    for row in registry.data_roots:
        matching = [path for path in tracked if path.startswith(row.root)]
        if not matching:
            raise ValueError(f"declared data root has no tracked files: {row.root}")
        for evidence in row.provenance_evidence:
            target = root / evidence
            if not target.is_file() or evidence not in tracked:
                raise ValueError(f"data provenance evidence is missing or untracked: {evidence}")
        if DataSourceType.public_third_party in row.source_types:
            lowered = row.license_status.lower()
            if not any(token in lowered for token in ("mit", "apache", "cc by", "bsd")):
                raise ValueError(f"third-party data license is not actionable: {row.root}")


def _verify_dependency_audit(audit: DependencyAudit, root: Path) -> None:
    if _sha256(root / "uv.lock") != audit.uv_lock_sha256:
        raise ValueError("dependency audit uv.lock hash drifted")
    if _sha256(root / "frontend/package-lock.json") != audit.package_lock_sha256:
        raise ValueError("dependency audit package-lock hash drifted")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    python_declared: set[str] = set()
    for requirement in project["project"]["dependencies"]:
        python_declared.add(_package_name(requirement))
    for requirements in project["project"].get("optional-dependencies", {}).values():
        python_declared.update(_package_name(item) for item in requirements)
    for requirements in project.get("dependency-groups", {}).values():
        python_declared.update(_package_name(item) for item in requirements)
    python_audited = {_normalize_package(row.package) for row in audit.python}
    if python_declared != python_audited:
        raise ValueError("Python direct dependency license inventory is incomplete or extra")

    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    npm_declared = set(package.get("dependencies", {})) | set(
        package.get("devDependencies", {})
    )
    npm_audited = {row.package for row in audit.npm}
    if npm_declared != npm_audited:
        raise ValueError("npm direct dependency license inventory is incomplete or extra")


def _verify_repository_license(
    decision: RepositoryLicenseDecision,
    root: Path,
    tracked: set[str],
) -> None:
    expected_exclusions = {
        "third-party source-page content under data/public_corpus/",
        "third-party copied source-page content under data/hard_negative_corpus/",
        "21 upstream Kubernetes documents under data/ops_runbook_corpus/",
    }
    if set(decision.excludes) != expected_exclusions or decision.applies_to != [
        "project-authored code, documentation, configuration, synthetic data, "
        "labels, overlays and original metadata"
    ]:
        raise ValueError("repository license scope or exclusions drifted")
    required = {
        decision.license_path: decision.license_sha256,
        decision.third_party_notices_path: decision.third_party_notices_sha256,
    }
    for path, expected_hash in required.items():
        target = root / path
        if path not in tracked or not target.is_file():
            raise ValueError(f"repository license artifact is missing or untracked: {path}")
        if _sha256(target) != expected_hash:
            raise ValueError(f"repository license artifact hash drifted: {path}")

    license_text = (root / decision.license_path).read_text(encoding="utf-8")
    if (
        "Apache License" not in license_text
        or "Version 2.0, January 2004" not in license_text
        or "http://www.apache.org/licenses/" not in license_text
    ):
        raise ValueError("LICENSE is not the audited Apache-2.0 license text")

    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    if project["project"].get("license") != decision.spdx_identifier:
        raise ValueError("Python project license metadata drifted")
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    if package.get("license") != decision.spdx_identifier:
        raise ValueError("frontend package license metadata drifted")


def _verify_third_party_materials(
    registry: PublicRepositoryAuditRegistry,
    root: Path,
    tracked: set[str],
) -> None:
    expected = {
        "FastAPI documentation": {
            "paths": {"data/public_corpus/", "data/hard_negative_corpus/"},
            "spdx": "MIT",
            "license": "LICENSES/FASTAPI-MIT.txt",
            "tokens": ("The MIT License", "Sebastián Ramírez"),
            "min_size": 900,
        },
        "Kubernetes documentation": {
            "paths": {"data/ops_runbook_corpus/"},
            "spdx": "CC-BY-4.0",
            "license": "LICENSES/KUBERNETES-CC-BY-4.0.txt",
            "tokens": (
                "Creative Commons Attribution 4.0 International Public License",
                "Section 3 -- License Conditions.",
            ),
            "min_size": 15_000,
        },
    }
    actual = {item.name: item for item in registry.third_party_materials}
    if set(actual) != set(expected):
        raise ValueError("third-party material inventory is incomplete or extra")
    excluded = set(registry.repository_license.excludes)
    notice = (root / registry.repository_license.third_party_notices_path).read_text(
        encoding="utf-8"
    )
    for name, contract in expected.items():
        item = actual[name]
        if (
            set(item.path_prefixes) != contract["paths"]
            or item.spdx_identifier != contract["spdx"]
            or item.license_copy_path != contract["license"]
        ):
            raise ValueError(f"third-party material scope or SPDX drifted: {name}")
        if any(
            not any(prefix in exclusion for exclusion in excluded)
            for prefix in item.path_prefixes
        ):
            raise ValueError(f"third-party material is not excluded from Apache-2.0: {name}")
        target = root / item.license_copy_path
        if item.license_copy_path not in tracked or not target.is_file():
            raise ValueError(f"third-party license copy is missing or untracked: {name}")
        if _sha256(target) != item.license_copy_sha256:
            raise ValueError(f"third-party license copy hash drifted: {name}")
        text = target.read_text(encoding="utf-8")
        if (
            target.stat().st_size < contract["min_size"]
            or any(token not in text for token in contract["tokens"])
        ):
            raise ValueError(f"third-party license copy content drifted: {name}")
        if (
            name not in notice
            or item.spdx_identifier not in notice
            or item.source_repository not in notice
            or item.copyright_notice not in notice
        ):
            raise ValueError(f"third-party attribution notice is incomplete: {name}")
    expected_root_spdx = {
        "data/public_corpus/": "MIT",
        "data/hard_negative_corpus/": "MIT",
        "data/ops_runbook_corpus/": "CC-BY-4.0",
    }
    audited_roots = {
        row.root: row
        for row in registry.data_roots
        if DataSourceType.public_third_party in row.source_types
    }
    if set(audited_roots) != set(expected_root_spdx):
        raise ValueError("third-party data-root inventory is incomplete or extra")
    for path, spdx in expected_root_spdx.items():
        row = audited_roots[path]
        if (
            spdx not in row.license_status
            or row.redistribution_status.value != "upstream-license-with-attribution"
        ):
            raise ValueError(f"third-party data was incorrectly relicensed: {path}")


def _verify_tracked_ignored_boundary(
    registry: PublicRepositoryAuditRegistry,
    root: Path,
    tracked: set[str],
) -> None:
    ignored_tracked = set(_git_lines(root, "ls-files", "-ci", "--exclude-standard"))
    declared_exceptions = set(registry.tracked_ignored_exceptions)
    if ignored_tracked != declared_exceptions:
        raise ValueError(
            "tracked/ignored exception closure failed: "
            f"actual={sorted(ignored_tracked)}, declared={sorted(declared_exceptions)}"
        )
    forbidden = [
        path
        for path in tracked
        if any(path.startswith(prefix) for prefix in IGNORED_GENERATED_PREFIXES)
    ]
    if forbidden:
        raise ValueError(f"ignored/generated boundary contains tracked files: {forbidden}")


def _verify_showcase_claim_isolation(
    registry: PublicRepositoryAuditRegistry,
    root: Path,
) -> None:
    for path in registry.formal_claim_surfaces:
        target = root / path
        if not target.is_file() or not _tracked(root, path):
            raise ValueError(f"formal claim surface is missing or untracked: {path}")
        verify_formal_surface_text(path, target.read_text(encoding="utf-8"))
    claim_registry = json.loads(
        (root / "data/claims/claim_registry.json").read_text(encoding="utf-8")
    )
    source_paths = {
        source["path"]
        for claim in claim_registry["claims"]
        for source in claim["source_artifacts"]
    }
    if any(path.startswith("data/showcase/") for path in source_paths):
        raise ValueError("showcase corpus is a formal claim source")


def _verify_legacy_codename(
    registry: PublicRepositoryAuditRegistry,
    root: Path,
    tracked: set[str],
) -> None:
    for path in sorted(tracked):
        text = _read_text(root / path)
        if text is not None:
            verify_legacy_codename_path(path, text, registry)


def _verify_public_brand(registry: PublicRepositoryAuditRegistry, root: Path) -> None:
    for path in registry.public_brand_surfaces:
        target = root / path
        if not target.is_file() or not _tracked(root, path):
            raise ValueError(f"public brand surface is missing or untracked: {path}")
        text = target.read_text(encoding="utf-8")
        expected = registry.public_project_name
        if path == "pyproject.toml":
            project = tomllib.loads(text)["project"]
            if (
                project["name"] != registry.legacy_python_distribution_name
                or project["description"] != registry.public_subtitle
            ):
                raise ValueError("Python package metadata changed its audited brand boundary")
            continue
        if path == "frontend/package.json":
            package = json.loads(text)
            if package["name"] != registry.frontend_package_name:
                raise ValueError("frontend package metadata changed its public brand")
            continue
        if expected not in text:
            raise ValueError(f"public brand is absent from surface: {path}")
    for path in (*root.glob("frontend/src/**/*.astro"), *root.glob("app/web/**/*.html")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"<img\b[^>]*>", text, re.IGNORECASE):
            if not re.search(r"\balt\s*=", match.group(0), re.IGNORECASE):
                raise ValueError(f"public image lacks alt text: {path.relative_to(root)}")
    for path in (root / "README.md", *root.glob("docs/*.md"), *root.glob("frontend/*.md")):
        if path.is_file() and re.search(r"!\[\]\(", path.read_text(encoding="utf-8")):
            raise ValueError(f"Markdown image lacks alt text: {path.relative_to(root)}")


def _scan_repository_text(
    registry: PublicRepositoryAuditRegistry,
    root: Path,
    tracked: set[str],
) -> dict[str, int]:
    secret_findings = 0
    pii_findings = 0
    for path in sorted(tracked):
        text = _read_text(root / path)
        if text is None:
            continue
        findings = scan_sensitive_text(
            path,
            text,
            registry.secret_fixture_path_prefixes,
        )
        secret_findings += sum(item.startswith("secret:") for item in findings)
        pii_findings += sum(item.startswith("pii:") for item in findings)
        if findings:
            raise ValueError(f"sensitive material found in {path}: {sorted(findings)}")
    return {
        "secret_findings": secret_findings,
        "pii_findings": pii_findings,
    }


def _tracked_paths(root: Path) -> set[str]:
    return set(_git_lines(root, "ls-files"))


def _tracked(root: Path, path: str) -> bool:
    return (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    )


def _git_lines(root: Path, *args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or "git command failed")
    return [line.replace("\\", "/") for line in completed.stdout.splitlines() if line]


def _read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw or len(raw) > 5_000_000:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _package_name(requirement: str) -> str:
    match = re.match(r"^([A-Za-z0-9_.-]+)", requirement)
    if not match:
        raise ValueError(f"could not parse dependency requirement: {requirement}")
    return _normalize_package(match.group(1))


def _normalize_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
