from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_boundary_a import (
    verify_boundary_a_evidence,
    write_boundary_a_evidence,
)
from app.eval.q5_frontier import (
    FRONTIER_ARTIFACT_FILES,
    verify_frontier_artifacts,
    write_frontier_artifacts,
)


@pytest.fixture()
def frontier_dir(tmp_path: Path) -> Path:
    target = tmp_path / "dev"
    write_frontier_artifacts(target)
    return target


@pytest.fixture(scope="module")
def boundary_kwargs() -> dict[str, Path]:
    payload = {
        "v3_run": Path(
            "data/eval_runs/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3"
        ),
        "v3_gold": Path("data/q5/archive/dev-v3/gold.jsonl"),
        "v4_run": Path("data/eval_runs/q5-dev-v4-mock-ir-7a9bf34-primary-k3"),
        "v4_gold": Path("data/q5/dev/gold.jsonl"),
        "value_dir": Path(
            "data/eval_runs/q5-dev-v4-value-ir-7a9bf34-primary-k3"
        ),
        "symbolic_dir": Path(
            "data/eval_runs/q5-dev-v4-symbolic-ir-7a9bf34-primary-k3"
        ),
        "receipt_path": Path(
            "data/eval_runs/q5-dev-v4-preflight-ir-7a9bf34-primary-k3.json"
        ),
        "dataset_root": Path("data/q5/dev"),
    }
    required = [
        payload["v3_run"],
        payload["v3_gold"],
        payload["v4_run"],
        payload["v4_gold"],
        payload["value_dir"],
        payload["symbolic_dir"],
        payload["receipt_path"],
        payload["dataset_root"],
    ]
    if any(not path.exists() for path in required):
        pytest.skip("local verified Boundary A source artifacts are absent")
    return payload


def test_frontier_topology_baselines_preregistration_and_leakage(frontier_dir) -> None:
    manifest = verify_frontier_artifacts(frontier_dir)
    assert manifest["protocol_namespace"] == "q5-frontier-v5"
    assert manifest["case_count"] == 48
    assert manifest["capability_class_counts"] == {
        "ambiguous_or_unsafe": 12,
        "semantic_open": 20,
        "symbolic_complete": 16,
    }
    assert manifest["policy_family_count"] == 4
    assert manifest["pair_count"] == 24
    assert manifest["pair_kind_counts"] == {
        "policy_fixed_state_changed": 12,
        "state_fixed_policy_changed": 12,
    }
    baseline = _json(frontier_dir / "baseline_manifest.json")
    assert baseline["acceptance"] == {
        "ambiguous_or_unsafe_unsafe_terminal_count": 0,
        "policy_ir_oracle_case_count": 48,
        "policy_ir_oracle_success_count": 48,
        "symbolic_complete_parser_coverage": 1.0,
        "symbolic_complete_wrong_execution_count": 0,
    }
    prereg = _json(frontier_dir / "claim_preregistration.json")
    assert prereg["primary_statistical_unit"] == "distinct_case"
    assert prereg["headline_requirements"]["beneficial_policy_family_minimum"] == 2
    assert prereg["semantic_open_parser_failure_required"] is False
    renderers = _json(frontier_dir / "renderer_manifest.json")
    assert len(renderers["dev_renderer_ids"]) == 3
    assert len(set(renderers["dev_renderer_sha256"].values())) == 3
    assert (
        renderers["reserved_test_renderer_namespace"]
        not in renderers["dev_renderer_ids"]
    )
    leakage = _json(frontier_dir / "leakage_report.json")
    assert leakage["valid"] is True
    assert leakage["leaked_runtime_keys"] == []
    assert not Path("data/q5_frontier/test").exists()
    assert not Path("data/q5_test").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate_runtime",
        "duplicate_topology",
        "cross_case_ir_transplant",
        "gold_leak",
        "renderer_downgrade",
        "source_hash_forgery",
        "self_report_readiness",
    ],
)
def test_frontier_mutation_matrix_fails_closed(
    frontier_dir: Path, tmp_path: Path, mutation: str
) -> None:
    target = tmp_path / mutation
    shutil.copytree(frontier_dir, target)
    if mutation == "missing":
        (target / "gold.jsonl").unlink()
    elif mutation == "extra":
        (target / "unsealed.json").write_text("{}\n", encoding="utf-8")
    elif mutation in {"duplicate_runtime", "duplicate_topology"}:
        name = (
            "runtime_cases.jsonl"
            if mutation == "duplicate_runtime"
            else "topology.jsonl"
        )
        rows = _jsonl(target / name)
        rows.append(rows[0])
        _write_jsonl(target / name, rows)
        _rehash_frontier(target)
    elif mutation == "cross_case_ir_transplant":
        rows = _jsonl(target / "policy_ir.jsonl")
        rows[0]["policy_ir"] = rows[1]["policy_ir"]
        _write_jsonl(target / "policy_ir.jsonl", rows)
        _rehash_frontier(target)
    elif mutation == "gold_leak":
        rows = _jsonl(target / "runtime_cases.jsonl")
        rows[0]["gold"] = {"disposition": "remediate"}
        _write_jsonl(target / "runtime_cases.jsonl", rows)
        _rehash_frontier(target)
    elif mutation == "renderer_downgrade":
        manifest = _json(target / "renderer_manifest.json")
        manifest["dev_test_renderer_reuse_forbidden"] = False
        _write_json(target / "renderer_manifest.json", manifest)
        _rehash_frontier(target)
    elif mutation == "source_hash_forgery":
        manifest = _json(target / "policy_ir_manifest.json")
        manifest["source_sha256"]["app/eval/q5_frontier.py"] = "0" * 64
        _write_json(target / "policy_ir_manifest.json", manifest)
        _rehash_frontier(target)
    else:
        prereg = _json(target / "claim_preregistration.json")
        prereg["readiness"] = "valid"
        prereg["claim_readiness_self_report_allowed"] = True
        _write_json(target / "claim_preregistration.json", prereg)
        _rehash_frontier(target)
    with pytest.raises(ValueError):
        verify_frontier_artifacts(target)


def test_boundary_a_is_hash_closed_and_scoped(
    tmp_path: Path, boundary_kwargs: dict[str, Path]
) -> None:
    target = tmp_path / "boundary"
    summary = write_boundary_a_evidence(target, **boundary_kwargs)
    assert verify_boundary_a_evidence(target, **boundary_kwargs) == summary
    assert summary["sources"]["v3_deepseek_real"]["real_run"] is True
    assert summary["sources"]["v4_deterministic_mock"]["real_run"] is False
    assert summary["scope_limits"] == {
        "general_natural_language_policy_extrapolation": False,
        "mock_used_for_real_claim": False,
        "v4_mock_is_real": False,
    }
    assert summary["evidence"]["v4_closed_vocabulary_symbolic_control"][
        "semantic_success"
    ] == 1.0
    assert summary["evidence"]["v4_value_ledger"]["value_class_counts"] == {
        "neutral": 108
    }
    assert summary["evidence"]["v4_value_ledger"]["beneficial_group_count"] == 0
    assert summary["evidence"]["v4_hybrid_incremental_value"]["llm_calls"] == 42
    assert summary["evidence"]["claim_readiness"]["core_blockers"] == [
        "claim_headroom",
        "beneficial_evidence_absent",
    ]


@pytest.mark.parametrize(
    ("artifact", "field"),
    [
        ("boundary_a_summary.json", "scope"),
        ("boundary_a_summary.json", "source"),
        ("boundary_a_summary.json", "readiness"),
        ("boundary_a_report.md", "report"),
    ],
)
def test_boundary_a_rehashed_mutations_fail_closed(
    tmp_path: Path,
    boundary_kwargs: dict[str, Path],
    artifact: str,
    field: str,
) -> None:
    source_dir = tmp_path / "original"
    write_boundary_a_evidence(source_dir, **boundary_kwargs)
    target = tmp_path / field
    shutil.copytree(source_dir, target)
    path = target / artifact
    if artifact.endswith(".md"):
        path.write_text(path.read_text(encoding="utf-8") + "\nforged\n", encoding="utf-8")
    else:
        summary = _json(path)
        if field == "scope":
            summary["scope_limits"]["general_natural_language_policy_extrapolation"] = True
        elif field == "source":
            summary["source_code_sha256"]["app/eval/q5_boundary_a.py"] = "0" * 64
        else:
            summary["evidence"]["claim_readiness"]["valid"] = True
        _write_json(path, summary)
    _rehash_boundary(target)
    with pytest.raises(ValueError):
        verify_boundary_a_evidence(target, **boundary_kwargs)


def test_frontier_artifact_closure_is_exact(frontier_dir: Path) -> None:
    assert {path.name for path in frontier_dir.iterdir()} == FRONTIER_ARTIFACT_FILES


def _rehash_frontier(target: Path) -> None:
    dataset_manifest_path = target / "frontier_dataset_manifest.json"
    dataset_manifest = _json(dataset_manifest_path)
    for name in list(dataset_manifest["row_sha256"]):
        dataset_manifest["row_sha256"][name] = _sha(target / name)
    _write_json(dataset_manifest_path, dataset_manifest)
    policy_manifest_path = target / "policy_ir_manifest.json"
    policy_manifest = _json(policy_manifest_path)
    policy_manifest["policy_ir_sha256"] = _sha(target / "policy_ir.jsonl")
    _write_json(policy_manifest_path, policy_manifest)
    hashes = {
        "schema_version": "q5-frontier-v5-hashes-v1",
        "artifacts": {
            path.name: _sha(path)
            for path in sorted(target.iterdir())
            if path.is_file() and path.name != "frontier_hashes.json"
        },
    }
    _write_json(target / "frontier_hashes.json", hashes)


def _rehash_boundary(target: Path) -> None:
    artifacts = {
        name: _sha(target / name)
        for name in ("boundary_a_report.md", "boundary_a_summary.json")
    }
    _write_json(
        target / "boundary_a_hashes.json",
        {"schema_version": "q5-boundary-a-hashes-v1", "artifacts": artifacts},
    )


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
