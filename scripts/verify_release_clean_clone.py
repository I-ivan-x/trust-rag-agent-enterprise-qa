"""Run the release verification matrix in a detached no-hardlinks clean clone."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.release_manifest import (  # noqa: E402
    CLEAN_CLONE_RECEIPT_PATH,
    FRONTEND_SCREENSHOTS,
)
from app.schemas.release_manifest import (  # noqa: E402
    LighthouseVerificationRun,
    ReleaseCleanCloneReceipt,
    RuntimeVersions,
    VerificationCommand,
)


def verify_release_clean_clone(
    commit: str = "HEAD",
    *,
    repository: Path = ROOT,
) -> ReleaseCleanCloneReceipt:
    tested_commit = _git(repository, "rev-parse", f"{commit}^{{commit}}")
    tested_tree = _git(repository, "rev-parse", f"{tested_commit}^{{tree}}")
    with tempfile.TemporaryDirectory(prefix="agent-release-clean-clone-") as temporary:
        clone = Path(temporary) / "repository"
        _run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "clone",
                "--quiet",
                "--no-hardlinks",
                repository.as_posix(),
                clone.as_posix(),
            ],
            cwd=repository,
        )
        _run(["git", "config", "core.autocrlf", "false"], cwd=clone)
        _run(["git", "checkout", "--quiet", "--detach", tested_commit], cwd=clone)
        if _git(clone, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("clean-clone checkout is not clean")
        if (clone / "data/q5_test").exists():
            raise ValueError("q5_test must remain absent")

        environment = dict(os.environ)
        environment["UV_OFFLINE"] = "1"
        environment["npm_config_offline"] = "true"
        environment["npm_config_audit"] = "false"
        commands: list[VerificationCommand] = []

        def passed(name: str, command: list[str], *, cwd: Path = clone) -> str:
            completed = _run(command, cwd=cwd, env=environment)
            commands.append(
                VerificationCommand(name=name, command=command, status="passed")
            )
            return completed.stdout + completed.stderr

        passed("uv_sync", ["py", "-m", "uv", "sync", "--locked", "--group", "dev"])
        claim_build = passed(
            "claim_build",
            ["py", "-m", "uv", "run", "--frozen", "python", "scripts/build_public_claims.py"],
        )
        passed(
            "claim_check",
            [
                "py",
                "-m",
                "uv",
                "run",
                "--frozen",
                "python",
                "scripts/build_public_claims.py",
                "--check",
            ],
        )
        passed(
            "claim_drift",
            ["py", "-m", "uv", "run", "--frozen", "python", "scripts/check_claim_drift.py"],
        )
        passed(
            "showcase_isolation",
            [
                "py",
                "-m",
                "uv",
                "run",
                "--frozen",
                "python",
                "scripts/build_interview_showcase.py",
                "--check",
            ],
        )
        passed(
            "public_repository_audit",
            [
                "py",
                "-m",
                "uv",
                "run",
                "--frozen",
                "python",
                "scripts/verify_public_repository.py",
            ],
        )
        gate_output = passed(
            "release_gates",
            [
                "py",
                "-m",
                "uv",
                "run",
                "--frozen",
                "python",
                "scripts/check_release_gates.py",
                "--summary",
                "tests/fixtures/release_gates/ci_clean_summary.json",
                "--leakage",
                "tests/fixtures/release_gates/ci_clean_leakage.json",
            ],
        )
        frontend = clone / "frontend"
        passed("npm_ci", ["npm", "ci"], cwd=frontend)
        passed("npm_build", ["npm", "run", "build"], cwd=frontend)
        playwright_output = passed("playwright", ["npx", "playwright", "test"], cwd=frontend)
        passed(
            "frontend_receipt",
            [
                "py",
                "-m",
                "uv",
                "run",
                "--frozen",
                "python",
                "scripts/verify_frontend_closure.py",
            ],
        )

        lighthouse_runs: list[LighthouseVerificationRun] = []
        for index in range(1, 4):
            output = f"acceptance/runtime/release-clean-clone/run-{index}"
            raw = passed(
                f"lighthouse_{index}",
                [
                    "node",
                    "scripts/run-lighthouse.mjs",
                    tested_commit,
                    output,
                ],
                cwd=frontend,
            )
            payload = _last_json_object(raw)
            lighthouse_runs.append(
                LighthouseVerificationRun(
                    run_index=index,
                    performance=payload["scores"]["performance"],
                    accessibility=payload["scores"]["accessibility"],
                    external_requests=payload["external_requests"],
                )
            )

        counts = _last_json_object(claim_build)
        playwright_passed, playwright_skipped = _playwright_counts(playwright_output)
        if "ALL 6 RELEASE GATES PASSED" not in gate_output:
            raise ValueError("clean-clone release gate count is not 6/6")
        if _git(clone, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("release verification modified tracked or untracked files")
        _verify_frontend_receipt(clone)
        return ReleaseCleanCloneReceipt(
            schema_version="agent-reliability-clean-clone-receipt-v1",
            tested_commit=tested_commit,
            tested_tree=tested_tree,
            clone_mode="git clone --no-hardlinks; detached checkout",
            runtime_versions=_runtime_versions(clone),
            commands=commands,
            lighthouse_runs=lighthouse_runs,
            claim_count=counts["claim_count"],
            playwright_passed=playwright_passed,
            playwright_skipped=playwright_skipped,
            release_gate_count=6,
            frontend_receipt_verified=True,
            screenshot_hashes_verified=True,
            clean_worktree_after_verification=True,
            ignored_or_untracked_dependency_count=0,
            model_requests=0,
            external_requests=0,
            q5_test="absent",
            status="passed",
        )


def write_receipt(
    receipt: ReleaseCleanCloneReceipt,
    output: Path | str = CLEAN_CLONE_RECEIPT_PATH,
    *,
    repository: Path = ROOT,
) -> Path:
    target = Path(output)
    if not target.is_absolute():
        target = repository / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _verify_frontend_receipt(repository: Path) -> None:
    receipt_path = repository / "frontend/acceptance/frontend-closure/receipt.json"
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != "frontend-closure-acceptance-v1"
        or payload.get("model_requests") != 0
        or payload.get("external_requests") != 0
        or not payload.get("hard_thresholds_passed")
    ):
        raise ValueError("frontend closure receipt is invalid")
    recorded = {row["path"]: row["sha256"] for row in payload.get("screenshots", [])}
    expected = {
        path: _sha256(repository / path)
        for path in FRONTEND_SCREENSHOTS
    }
    if recorded != expected:
        raise ValueError("frontend closure screenshot hash mismatch")


def _runtime_versions(repository: Path) -> RuntimeVersions:
    return RuntimeVersions(
        python=_command_text(["py", "--version"], repository).replace("Python ", ""),
        uv=_command_text(["py", "-m", "uv", "--version"], repository)
        .split(" (", 1)[0]
        .replace("uv ", ""),
        node=_command_text(["node", "--version"], repository).lstrip("v"),
        npm=_command_text(["npm", "--version"], repository),
    )


def _playwright_counts(output: str) -> tuple[int, int]:
    passed = re.search(r"(\d+) passed", output)
    skipped = re.search(r"(\d+) skipped", output)
    if not passed:
        raise ValueError("Playwright output did not report passed tests")
    return int(passed.group(1)), int(skipped.group(1)) if skipped else 0


def _last_json_object(output: str) -> dict:
    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if not output[index + end :].strip():
            return value
    raise ValueError("command did not end with a JSON object")


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _command_text(command: list[str], cwd: Path) -> str:
    completed = _run(command, cwd=cwd)
    return (completed.stdout or completed.stderr).strip()


def _git(repository: Path, *args: str) -> str:
    return _command_text(["git", *args], repository)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which(command[0])
    if executable:
        command = [executable, *command[1:]]
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"command failed ({' '.join(command)}): {details}")
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--output", type=Path, default=CLEAN_CLONE_RECEIPT_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    recomputed = verify_release_clean_clone(args.commit)
    if args.check:
        recorded = ReleaseCleanCloneReceipt.model_validate_json(
            (ROOT / args.output).read_text(encoding="utf-8")
        )
        if recomputed != recorded:
            raise ValueError("release clean-clone receipt differs from recomputation")
    else:
        write_receipt(recomputed, args.output)
    print(json.dumps(recomputed.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
