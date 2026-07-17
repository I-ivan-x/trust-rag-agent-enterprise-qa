from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_frontier_k0t_dev import (
    K0T_DEV_FILES,
    K0T_PREREG_COMMIT,
    verify_k0t_dev,
    write_k0t_dev,
)


@pytest.fixture()
def k0t_dev(tmp_path: Path) -> Path:
    target = tmp_path / "k0t-dev"
    write_k0t_dev(target)
    return target


def test_k0t_dev_topology_metrics_and_balance(k0t_dev: Path) -> None:
    manifest = verify_k0t_dev(k0t_dev)
    assert {item.name for item in k0t_dev.iterdir()} == K0T_DEV_FILES
    assert manifest["case_count"] == 96
    assert manifest["capability_counts"] == {
        "symbolic_complete": 16,
        "semantic_open": 64,
        "ambiguous_or_unsafe": 16,
    }
    assert manifest["semantic_coverage_counts"] == {
        "parser_covered": 32,
        "parser_uncovered": 32,
    }
    metrics = _json(k0t_dev / "metric_report.json")
    assert metrics["deterministic_conditional_risk"] == 0.0
    assert metrics["parser_uncovered"] == 32
    assert metrics["semantic_call_avoidance"] == 0.5
    assert metrics["unsafe_terminal"] == 0
    assert metrics["model_requests"] == 0


def test_k0t_counterfactual_and_mapping_constraints(k0t_dev: Path) -> None:
    coverage = _json(k0t_dev / "coverage_report.json")
    assert coverage["semantic_pair_direction_counts"] == {
        "pair_count": 32,
        "policy_fixed_state_changed": 32,
        "state_fixed_policy_changed": 32,
    }
    assert coverage["semantic_pair_direction_by_coverage"] == {
        "parser_covered": {
            "policy_fixed_state_changed": 8,
            "state_fixed_policy_changed": 8,
        },
        "parser_uncovered": {
            "policy_fixed_state_changed": 8,
            "state_fixed_policy_changed": 8,
        },
    }
    assert all(len(actions) == 4 for actions in coverage["family_actions"].values())
    assert all(len(actions) == 4 for actions in coverage["phenomenon_actions"].values())
    assert len(coverage["false_branch_dispositions"]) == 4
    assert coverage["phenomena_cross_all_families"] is True
    assert coverage["policy_state_values_are_label_neutral"] is True
    assert coverage["observed_action_phrase_count"] >= 16


def test_prereg_receipt_anchors_a_sources(k0t_dev: Path) -> None:
    receipt = _json(k0t_dev / "prereg_receipt.json")
    assert receipt["prereg_commit"] == K0T_PREREG_COMMIT
    for path, identity in receipt["frozen_sources"].items():
        assert identity["source_sha256"] == hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "gold",
        "topology",
        "policy_value",
        "receipt",
        "graded",
    ],
)
def test_k0t_b_rehashed_mutations_fail_closed(
    k0t_dev: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    target = tmp_path / mutation
    shutil.copytree(k0t_dev, target)
    if mutation == "missing":
        (target / "coverage_report.json").unlink()
    elif mutation == "extra":
        (target / "extra.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "gold":
        rows = _jsonl(target / "gold.jsonl")
        rows[16]["disposition"] = "human_review"
        _write_jsonl(target / "gold.jsonl", rows)
        _rehash(target)
    elif mutation == "topology":
        rows = _jsonl(target / "topology.jsonl")
        rows[16]["policy_family"] = "change"
        _write_jsonl(target / "topology.jsonl", rows)
        _rehash(target)
    elif mutation == "policy_value":
        rows = _jsonl(target / "policy_ir.jsonl")
        rows[16]["policy_ir"]["condition"]["all_of"][0]["value"] = "action_notify"
        _write_jsonl(target / "policy_ir.jsonl", rows)
        _rehash(target)
    elif mutation == "receipt":
        payload = _json(target / "prereg_receipt.json")
        payload["prereg_commit"] = "0" * 40
        _write_json(target / "prereg_receipt.json", payload)
        _rehash(target)
    else:
        rows = _jsonl(target / "graded_rows.jsonl")
        rows[16]["success"] = not rows[16]["success"]
        _write_jsonl(target / "graded_rows.jsonl", rows)
        _rehash(target)
    with pytest.raises(ValueError):
        verify_k0t_dev(target)


def _rehash(target: Path) -> None:
    artifacts = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(target.iterdir())
        if item.is_file() and item.name != "artifact_hashes.json"
    }
    _write_json(
        target / "artifact_hashes.json",
        {"schema_version": "q5-k0t-dev-hashes-v1", "artifacts": artifacts},
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
