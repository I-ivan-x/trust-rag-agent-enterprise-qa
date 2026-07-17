from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_frontier_k0u_dev import K0U_DEV_FILES, verify_k0u_dev, write_k0u_dev


@pytest.fixture()
def dev_dir(tmp_path: Path) -> Path:
    target = tmp_path / "dev"
    write_k0u_dev(target)
    return target


def test_k0u_handwritten_topology_and_pre_audit_metrics(dev_dir: Path) -> None:
    manifest = verify_k0u_dev(dev_dir)
    assert {item.name for item in dev_dir.iterdir()} == K0U_DEV_FILES
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
    metrics = _json(dev_dir / "metric_report.json")
    assert metrics["deterministic_complete_count"] == 32
    assert metrics["deterministic_conditional_risk"] == 0
    assert metrics["oracle_resolvable_abstentions"] == 32
    assert metrics["hybrid_theoretical_call_avoidance"] == 0.5
    assert metrics["unsafe_terminal"] == 0


def test_k0u_policy_inventory_is_explicit_and_balanced(dev_dir: Path) -> None:
    coverage = _json(dev_dir / "coverage_report.json")
    assert coverage["handwritten_inventory_count"] == 64
    assert coverage["unique_semantic_policy_text_count"] >= 40
    assert coverage["authoring_joined_string_count"] == 0
    assert coverage["semantic_batch_renderer_present"] is False
    assert len(coverage["phenomenon_counts"]) == 8
    assert all(len(actions) == 4 for actions in coverage["family_actions"].values())
    assert len(set(coverage["global_action_counts"].values())) == 1
    assert all(len(actions) == 4 for actions in coverage["phenomenon_actions"].values())
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
    assert coverage["pair_constraints_verified"] == {
        "policy_fixed_state_changed": 16,
        "state_fixed_policy_changed": 16,
    }


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "gold", "runtime", "inventory", "receipt", "graded"],
)
def test_k0u_dev_rehashed_mutations_fail_closed(
    dev_dir: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    target = tmp_path / mutation
    shutil.copytree(dev_dir, target)
    if mutation == "missing":
        (target / "coverage_report.json").unlink()
    elif mutation == "extra":
        (target / "extra.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "gold":
        rows = _jsonl(target / "gold.jsonl")
        rows[16]["disposition"] = "human_review"
        _write_jsonl(target / "gold.jsonl", rows)
        _rehash(target)
    elif mutation == "runtime":
        rows = _jsonl(target / "runtime_cases.jsonl")
        rows[16]["policy_text"] += "\nForged instruction."
        _write_jsonl(target / "runtime_cases.jsonl", rows)
        _rehash(target)
    elif mutation == "inventory":
        rows = _jsonl(target / "policy_inventory.jsonl")
        rows[0]["policy_text_sha256"] = "0" * 64
        _write_jsonl(target / "policy_inventory.jsonl", rows)
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
        verify_k0u_dev(target)


def _rehash(target: Path) -> None:
    artifacts = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(target.iterdir())
        if item.is_file() and item.name != "artifact_hashes.json"
    }
    _write_json(
        target / "artifact_hashes.json",
        {"schema_version": "q5-k0u-dev-hashes-v1", "artifacts": artifacts},
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
