from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.eval.q5_boundary_b import verify_boundary_b
from app.eval.q5_boundary_c import verify_boundary_c
from app.eval.q5_frontier import verify_frontier_artifacts
from app.eval.q5_frontier_parser_uncovered_v4 import (
    PACKAGE_FILES,
    PREREG_COMMIT,
    verify_parser_uncovered_dev_v4,
    write_parser_uncovered_dev_v4,
)
from app.eval.q5_frontier_prereg_v4 import verify_preregistration_v4
from app.eval.q5_frontier_v2 import verify_frontier_v2_artifacts
from app.eval.q5_frontier_v3 import verify_frontier_v3_artifacts


@pytest.fixture()
def package(tmp_path: Path) -> Path:
    target = tmp_path / "parser_uncovered_dev"
    write_parser_uncovered_dev_v4(target)
    return target


def test_parser_uncovered_package_meets_preregistered_headroom(package: Path) -> None:
    manifest = verify_parser_uncovered_dev_v4(package)
    assert {item.name for item in package.iterdir()} == PACKAGE_FILES
    assert manifest["partition"] == "parser_uncovered_dev"
    assert manifest["case_count"] == 80
    assert manifest["parser_uncovered_case_count"] == 16
    assert manifest["family_count"] == 4
    assert manifest["phenomenon_count"] == 4
    headroom = _json(package / "headroom_report.json")
    assert set(headroom) == {
        "schema_version",
        "oracle_resolvable_abstentions",
        "family_coverage",
        "phenomenon_coverage",
        "deterministic_conditional_risk",
        "call_headroom",
        "token_avoidance",
    }
    assert headroom["oracle_resolvable_abstentions"] == 16
    assert headroom["deterministic_conditional_risk"] == 0.0
    assert headroom["token_avoidance"] == "not_evaluated"
    assert "beneficial" not in json.dumps(headroom).lower()


def test_semantic_authoring_is_diverse_and_suite_abstains(package: Path) -> None:
    topology = {row["runtime_ref"]: row for row in _jsonl(package / "topology.jsonl")}
    runtime = {row["runtime_ref"]: row for row in _jsonl(package / "runtime_cases.jsonl")}
    execution = {row["runtime_ref"]: row for row in _jsonl(package / "execution_rows.jsonl")}
    refs = [ref for ref, row in topology.items() if row["capability_class"] == "semantic_open"]
    assert len(refs) == 16
    assert len({runtime[ref]["policy_text"] for ref in refs}) == 16
    assert all(execution[ref]["parser_status"] == "abstain" for ref in refs)
    old_aliases = {
        "retire the stale record",
        "open an intervention ticket",
        "send the designated notice",
        "transfer the decision to a human reviewer",
        "leave the governed record unchanged",
    }
    assert not any(alias in runtime[ref]["policy_text"] for ref in refs for alias in old_aliases)


def test_receipt_records_commit_blob_and_source_sha(package: Path) -> None:
    receipt = _json(package / "prereg_receipt.json")
    assert receipt["prereg_commit"] == PREREG_COMMIT
    for path, identity in receipt["frozen_sources"].items():
        blob = _git("rev-parse", f"{PREREG_COMMIT}:{path}")
        assert identity["git_blob_sha"] == blob
        assert identity["source_sha256"] == hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("category", "mutation"),
    [
        ("structural", "missing_artifact"),
        ("structural", "extra_artifact"),
        ("semantic", "gold_disposition"),
        ("semantic", "policy_ir_clause"),
        ("artifact", "prereg_commit"),
        ("artifact", "parser_blob"),
        ("artifact", "rehashed_graded_row"),
    ],
)
def test_mutation_categories_fail_closed(
    package: Path,
    tmp_path: Path,
    category: str,
    mutation: str,
) -> None:
    target = tmp_path / f"{category}-{mutation}"
    shutil.copytree(package, target)
    if mutation == "missing_artifact":
        (target / "coverage_report.json").unlink()
    elif mutation == "extra_artifact":
        (target / "unexpected.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "gold_disposition":
        rows = _jsonl(target / "gold.jsonl")
        rows[0]["disposition"] = "human_review"
        _write_jsonl(target / "gold.jsonl", rows)
        _rehash(target)
    elif mutation == "policy_ir_clause":
        rows = _jsonl(target / "policy_ir.jsonl")
        rows[0]["policy_ir"]["condition"]["all_of"][0]["value"] = "forged"
        _write_jsonl(target / "policy_ir.jsonl", rows)
        _rehash(target)
    elif mutation == "prereg_commit":
        receipt = _json(target / "prereg_receipt.json")
        receipt["prereg_commit"] = "0" * 40
        _write_json(target / "prereg_receipt.json", receipt)
        _rehash(target)
    elif mutation == "parser_blob":
        receipt = _json(target / "prereg_receipt.json")
        first = next(iter(receipt["frozen_sources"].values()))
        first["git_blob_sha"] = "0" * 40
        _write_json(target / "prereg_receipt.json", receipt)
        _rehash(target)
    else:
        rows = _jsonl(target / "graded_rows.jsonl")
        rows[0]["success"] = not rows[0]["success"]
        _write_jsonl(target / "graded_rows.jsonl", rows)
        _rehash(target)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        verify_parser_uncovered_dev_v4(target)


def test_boundary_and_historical_packages_continue_to_verify() -> None:
    verify_frontier_artifacts("data/q5_frontier/dev")
    verify_frontier_v2_artifacts("data/q5_frontier/dev-v2")
    verify_frontier_v3_artifacts("data/q5_frontier/dev-v3")
    verify_preregistration_v4("data/q5_frontier/prereg-v4")
    boundary_b = Path("data/eval_runs/q5-boundary-b-k0s")
    boundary_c = Path("data/eval_runs/q5-boundary-c-k0sr")
    if boundary_b.exists():
        verify_boundary_b(boundary_b)
    if boundary_c.exists():
        verify_boundary_c(boundary_c)
    assert not Path("data/q5_test").exists()


def _rehash(target: Path) -> None:
    hashes = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(target.iterdir())
        if item.is_file() and item.name != "artifact_hashes.json"
    }
    _write_json(
        target / "artifact_hashes.json",
        {"schema_version": "q5-parser-uncovered-artifact-hashes-v1", "artifacts": hashes},
    )


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
