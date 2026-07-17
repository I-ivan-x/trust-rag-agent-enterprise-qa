from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_boundary_a import verify_boundary_a_evidence
from app.eval.q5_boundary_b import verify_boundary_b
from app.eval.q5_boundary_c import verify_boundary_c
from app.eval.q5_boundary_d import verify_boundary_d
from app.eval.q5_frontier import verify_frontier_artifacts
from app.eval.q5_frontier_k0t_audit import (
    AUDIT_FILES,
    verify_k0t_attack_audit,
    write_k0t_attack_audit,
)
from app.eval.q5_frontier_k0t_dev import verify_k0t_dev
from app.eval.q5_frontier_v2 import verify_frontier_v2_artifacts
from app.eval.q5_frontier_v3 import verify_frontier_v3_artifacts


@pytest.fixture()
def audit_dir(tmp_path: Path) -> Path:
    target = tmp_path / "audit"
    write_k0t_attack_audit(target)
    return target


def test_all_preregistered_shortcuts_preserve_headroom(audit_dir: Path) -> None:
    readiness = verify_k0t_attack_audit(audit_dir)
    assert {item.name for item in audit_dir.iterdir()} == AUDIT_FILES
    assert readiness["valid"] is True
    assert readiness["decision"] == "approved_for_separate_k1_real_model_evaluation"
    phrase_audit = readiness["action_phrase_audit"]
    assert phrase_audit["balanced"] is True
    assert set(phrase_audit["action_occurrence_counts"].values()) == {32}
    assert set(phrase_audit["phrase_occurrence_counts"].values()) == {8}
    audit = _json(audit_dir / "shortcut_audit.json")
    results = {item["name"]: item for item in audit["attacks"]}
    assert results["lexical_condition_action_parser"]["success_rate"] == 0.5
    assert results["pair_neighbor"]["success_rate"] == 0.5
    assert all(not item["breached"] for item in audit["attacks"])
    assert audit["model_requests"] == 0


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "attack", "readiness", "lineage", "source_hash"],
)
def test_k0t_c_rehashed_mutations_fail_closed(
    audit_dir: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    target = tmp_path / mutation
    shutil.copytree(audit_dir, target)
    if mutation == "missing":
        (target / "attack_report.md").unlink()
    elif mutation == "extra":
        (target / "extra.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "attack":
        payload = _json(target / "shortcut_audit.json")
        payload["attacks"][0]["success_rate"] = 0.75
        payload["attacks"][0]["breached"] = True
        payload["headroom_survives"] = False
        _write_json(target / "shortcut_audit.json", payload)
        _rehash(target)
    elif mutation == "readiness":
        payload = _json(target / "k1_readiness.json")
        payload["checks"]["shortcut_headroom"] = False
        _write_json(target / "k1_readiness.json", payload)
        _rehash(target)
    elif mutation == "lineage":
        payload = _json(target / "lineage_receipt.json")
        payload["data_commit"] = "0" * 40
        _write_json(target / "lineage_receipt.json", payload)
        _rehash(target)
    else:
        payload = _json(target / "source_dataset_hashes.json")
        first = next(iter(payload["artifacts"]))
        payload["artifacts"][first] = "0" * 64
        _write_json(target / "source_dataset_hashes.json", payload)
        _rehash(target)
    with pytest.raises(ValueError):
        verify_k0t_attack_audit(target)


def test_boundaries_and_historical_frontiers_verify() -> None:
    verify_frontier_artifacts("data/q5_frontier/dev")
    verify_frontier_v2_artifacts("data/q5_frontier/dev-v2")
    verify_frontier_v3_artifacts("data/q5_frontier/dev-v3")
    verify_k0t_dev("data/q5_frontier/dev-k0t")
    if Path("data/eval_runs/q5-boundary-b-k0s").exists():
        verify_boundary_b("data/eval_runs/q5-boundary-b-k0s")
    if Path("data/eval_runs/q5-boundary-c-k0sr").exists():
        verify_boundary_c("data/eval_runs/q5-boundary-c-k0sr")
    if Path("data/eval_runs/q5-boundary-d-k0t").exists():
        verify_boundary_d("data/eval_runs/q5-boundary-d-k0t")
    boundary_a = Path("data/eval_runs/q5-boundary-a-k0-ef75a6e")
    if boundary_a.exists():
        verify_boundary_a_evidence(
            boundary_a,
            v3_run=Path(
                "data/eval_runs/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3"
            ),
            v3_gold=Path("data/q5/archive/dev-v3/gold.jsonl"),
            v4_run=Path("data/eval_runs/q5-dev-v4-mock-ir-7a9bf34-primary-k3"),
            v4_gold=Path("data/q5/dev/gold.jsonl"),
            value_dir=Path("data/eval_runs/q5-dev-v4-value-ir-7a9bf34-primary-k3"),
            symbolic_dir=Path(
                "data/eval_runs/q5-dev-v4-symbolic-ir-7a9bf34-primary-k3"
            ),
            receipt_path=Path(
                "data/eval_runs/q5-dev-v4-preflight-ir-7a9bf34-primary-k3.json"
            ),
            dataset_root=Path("data/q5/dev"),
        )
    assert not Path("data/q5_test").exists()


def _rehash(target: Path) -> None:
    artifacts = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(target.iterdir())
        if item.is_file() and item.name != "audit_hashes.json"
    }
    _write_json(
        target / "audit_hashes.json",
        {"schema_version": "q5-k0t-audit-hashes-v1", "artifacts": artifacts},
    )


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
