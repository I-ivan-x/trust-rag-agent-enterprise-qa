from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_boundary_f_addendum import (
    ADDENDUM_FILES,
    SOURCE_HASHES,
    verify_boundary_f_addendum,
    write_boundary_f_addendum,
)


@pytest.fixture()
def addendum_dir(tmp_path: Path) -> Path:
    target = tmp_path / "addendum"
    write_boundary_f_addendum(target)
    return target


def test_addendum_recomputes_exact_frozen_scope_metrics(addendum_dir: Path) -> None:
    metrics = verify_boundary_f_addendum(addendum_dir)
    assert {item.name for item in addendum_dir.iterdir()} == ADDENDUM_FILES
    assert metrics == {
        "schema_version": "q5-boundary-f-addendum-metrics-v1",
        "claim_scope": "frozen K0U parser-uncovered 32-case scope",
        "case_count": 32,
        "parsed_count": 32,
        "correct_count": 32,
        "coverage": 1.0,
        "conditional_accuracy": 1.0,
        "conditional_risk": 0.0,
        "abstention_count": 0,
        "previously_uncovered_cases_resolved": {"resolved": 32, "total": 32},
        "remaining_uncovered_cases": {"count": 0, "total": 32},
        "controlled_prose_track": "closed",
        "k1_approved": False,
        "boundary_g_allowed": False,
        "new_k1_data_allowed": False,
        "model_requests": 0,
        "external_requests": 0,
    }
    scope = _json(addendum_dir / "frozen_scope.json")
    assert scope["runtime_ref_count"] == 32
    assert len(scope["runtime_refs"]) == len(set(scope["runtime_refs"])) == 32
    assert scope["source_artifact_sha256"] == SOURCE_HASHES


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_file",
        "extra_file",
        "duplicate_row",
        "missing_row",
        "extra_row",
        "prediction",
        "metrics",
        "scope",
        "lineage",
        "attestation",
        "canonical_hash",
    ],
)
def test_addendum_mutations_fail_closed(
    addendum_dir: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    target = tmp_path / mutation
    shutil.copytree(addendum_dir, target)
    if mutation == "missing_file":
        (target / "addendum_report.md").unlink()
    elif mutation == "extra_file":
        (target / "extra.json").write_text("{}\n", encoding="utf-8")
    elif mutation in {"duplicate_row", "missing_row", "extra_row", "prediction"}:
        rows = _jsonl(target / "addendum_rows.jsonl")
        if mutation == "duplicate_row":
            rows.append(dict(rows[0]))
        elif mutation == "missing_row":
            rows.pop()
        elif mutation == "extra_row":
            rows.append({**rows[0], "runtime_ref": "foreign-runtime-ref"})
        else:
            rows[0]["prediction"] = "human_review"
            rows[0]["correct"] = False
        _write_jsonl(target / "addendum_rows.jsonl", rows)
        _rehash(target)
    elif mutation == "canonical_hash":
        hashes = _json(target / "artifact_hashes.json")
        hashes["artifacts"]["addendum_metrics.json"] = "0" * 64
        _write_json(target / "artifact_hashes.json", hashes)
    else:
        names = {
            "metrics": "addendum_metrics.json",
            "scope": "frozen_scope.json",
            "lineage": "lineage_receipt.json",
            "attestation": "parser_attestation.json",
        }
        name = names[mutation]
        payload = _json(target / name)
        if mutation == "metrics":
            payload["conditional_risk"] = 1.0
        elif mutation == "scope":
            payload["runtime_refs"].pop()
        elif mutation == "lineage":
            payload["original_boundary_f_artifacts_modified"] = True
        else:
            payload["valid"] = False
        _write_json(target / name, payload)
        _rehash(target)
    with pytest.raises(ValueError):
        verify_boundary_f_addendum(target)


def _rehash(target: Path) -> None:
    artifacts = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(target.iterdir())
        if item.is_file() and item.name != "artifact_hashes.json"
    }
    _write_json(
        target / "artifact_hashes.json",
        {"schema_version": "q5-boundary-f-addendum-hashes-v1", "artifacts": artifacts},
    )


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
