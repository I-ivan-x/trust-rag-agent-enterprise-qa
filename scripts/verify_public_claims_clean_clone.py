"""Verify public claims from a detached clean clone and emit a tracked receipt payload."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.public_claims import CleanCloneVerificationReceipt  # noqa: E402


def verify_clean_clone(commit: str = "HEAD") -> CleanCloneVerificationReceipt:
    repository = _git(ROOT, "rev-parse", "--show-toplevel")
    tested_commit = _git(ROOT, "rev-parse", f"{commit}^{{commit}}")
    tested_tree = _git(ROOT, "rev-parse", f"{tested_commit}^{{tree}}")
    with tempfile.TemporaryDirectory(prefix="public-claims-clean-clone-") as temp:
        clone = Path(temp) / "repository"
        _run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "clone",
                "--quiet",
                "--no-hardlinks",
                "--no-local",
                repository,
                str(clone),
            ],
            cwd=ROOT,
        )
        _run(["git", "config", "core.autocrlf", "false"], cwd=clone)
        _run(["git", "checkout", "--quiet", "--detach", tested_commit], cwd=clone)
        if _git(clone, "status", "--porcelain"):
            raise ValueError("clean-clone verification checkout is not clean")
        completed = _run(
            [sys.executable, "scripts/build_public_claims.py", "--check"],
            cwd=clone,
        )
        counts = json.loads(completed.stdout.strip().splitlines()[-1])
        registry = json.loads(
            (clone / "data/claims/claim_registry.json").read_text(encoding="utf-8")
        )
        source_paths = {
            source["path"]
            for claim in registry["claims"]
            for source in claim["source_artifacts"]
        }
        raw_source_paths = {
            path for path in source_paths if path.startswith("data/claims/source/")
        }
        ignored_dependencies = [
            path
            for path in source_paths
            if not _is_tracked(clone, path)
            or _is_ignored(clone, path)
        ]
        if ignored_dependencies:
            raise ValueError(
                "claim verification depends on ignored/untracked files: "
                + ", ".join(sorted(ignored_dependencies))
            )
        if _git(clone, "status", "--porcelain"):
            raise ValueError("claim verification modified the clean clone")
        receipt = CleanCloneVerificationReceipt(
            schema_version="public-claim-clean-clone-receipt-v1",
            tested_commit=tested_commit,
            tested_tree=tested_tree,
            claim_count=counts["claim_count"],
            raw_source_count=len(raw_source_paths),
            source_blob_count=len(source_paths),
            generated_file_count=counts["generated_file_count"],
            ignored_file_dependency_count=0,
            schema_check="passed",
            source_lineage_check="passed",
            generator_check="passed",
        )
    return receipt


def verify_receipt(path: Path) -> CleanCloneVerificationReceipt:
    recorded = CleanCloneVerificationReceipt.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    recomputed = verify_clean_clone(recorded.tested_commit)
    if recomputed != recorded:
        raise ValueError("clean-clone verification receipt does not match recomputation")
    return recorded


def _is_tracked(repository: Path, path: str) -> bool:
    return (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            cwd=repository,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _is_ignored(repository: Path, path: str) -> bool:
    return (
        subprocess.run(
            ["git", "check-ignore", "--quiet", "--", path],
            cwd=repository,
            capture_output=True,
        ).returncode
        == 0
    )


def _git(repository: Path, *args: str) -> str:
    return _run(["git", *args], cwd=repository).stdout.strip()


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"command failed ({' '.join(command)}): {details}")
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = verify_receipt(args.receipt) if args.receipt else verify_clean_clone(args.commit)
    print(json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
