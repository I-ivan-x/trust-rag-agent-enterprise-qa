from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.eval.q5_boundary_a import verify_boundary_a_evidence
from app.eval.q5_boundary_b import verify_boundary_b, write_boundary_b
from app.eval.q5_frontier import verify_frontier_artifacts
from app.eval.q5_frontier_v2 import verify_frontier_v2_artifacts
from app.eval.q5_frontier_v3 import (
    FRONTIER_V3_FILES,
    verify_frontier_v3_artifacts,
    write_frontier_v3_artifacts,
)


@pytest.fixture()
def v3_dir(tmp_path: Path) -> Path:
    target = tmp_path / "dev-v3"
    write_frontier_v3_artifacts(target)
    return target


def test_boundary_b_closes_frozen_v2_and_proves_deterministic_20_of_20(
    tmp_path: Path,
) -> None:
    dev_v2 = Path("data/q5_frontier/dev-v2")
    before = _tree_hashes(dev_v2)
    target = tmp_path / "boundary-b"
    summary = write_boundary_b(target, dev_v2_dir=dev_v2)
    assert verify_boundary_b(target, dev_v2_dir=dev_v2) == summary
    assert summary["semantic_open_case_count"] == 20
    assert summary["deterministic_success_count"] == 20
    assert summary["deterministic_success_rate"] == 1.0
    assert summary["llm_calls"] == 0
    assert summary["external_requests"] == 0
    frozen = _json(target / "frozen_dev_v2_hashes.json")
    assert frozen["artifacts"] == before
    assert _tree_hashes(dev_v2) == before


@pytest.mark.parametrize("mutation", ["summary", "parser_rows", "frozen_hash", "source_hash"])
def test_boundary_b_rehashed_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    target = tmp_path / mutation
    write_boundary_b(target)
    if mutation == "summary":
        payload = _json(target / "boundary_b_summary.json")
        payload["deterministic_success_count"] = 19
        _write_json(target / "boundary_b_summary.json", payload)
    elif mutation == "parser_rows":
        rows = _jsonl(target / "parser_rows.jsonl")
        rows[0]["success"] = False
        _write_jsonl(target / "parser_rows.jsonl", rows)
    elif mutation == "frozen_hash":
        payload = _json(target / "frozen_dev_v2_hashes.json")
        first = next(iter(payload["artifacts"]))
        payload["artifacts"][first] = "0" * 64
        _write_json(target / "frozen_dev_v2_hashes.json", payload)
    else:
        payload = _json(target / "boundary_b_summary.json")
        first = next(iter(payload["source_code_sha256"]))
        payload["source_code_sha256"][first] = "0" * 64
        _write_json(target / "boundary_b_summary.json", payload)
    _rehash_boundary(target)
    with pytest.raises(ValueError):
        verify_boundary_b(target)


def test_v3_topology_renderers_attestation_compiler_and_headroom(v3_dir: Path) -> None:
    manifest = verify_frontier_v3_artifacts(v3_dir)
    assert {item.name for item in v3_dir.iterdir()} == FRONTIER_V3_FILES
    assert manifest["case_count"] == 64
    assert manifest["capability_class_counts"] == {
        "symbolic_complete": 16,
        "semantic_open": 32,
        "ambiguous_or_unsafe": 16,
    }
    assert manifest["policy_family_counts"] == {
        "access": 16,
        "change": 16,
        "incident": 16,
        "retention": 16,
    }
    assert manifest["pair_audit"]["pair_count"] == 32
    assert manifest["pair_audit"]["pair_kind_counts"] == {
        "policy_fixed_state_changed": 16,
        "state_fixed_policy_changed": 16,
    }
    coverage = manifest["ir_coverage_matrix"]
    assert set(coverage["predicate_operator_counts"]) == {"eq", "ne", "in"}
    assert coverage["all_of_case_count"] == 64
    assert coverage["any_of_case_count"] > 0
    assert set(coverage["precedence_counts"]) == {
        "base_only",
        "exception_overrides",
        "deny_overrides",
    }
    assert coverage["scope_mismatch_count"] > 0
    assert coverage["temporal_mismatch_count"] > 0
    assert coverage["unauthorized_count"] > 0
    assert coverage["observation_failure_count"] > 0
    renderer = _json(v3_dir / "renderer_manifest.json")
    assert renderer["renderer_family_count"] >= 4
    assert renderer["parser_suite_and_renderer_authoring_source_separated"] is True
    assert renderer["unique_policy_text_count"] == 48
    assert renderer["policy_text_multiplicity"] == {"1": 32, "2": 16}
    assert renderer["semantic_open_uses_canonical_action_wording"] is False
    attestation = _json(v3_dir / "semantic_attestation_manifest.json")
    assert attestation["closed_vocabulary_exact_binding"] is True
    assert attestation["semantic_correctness_is_runtime_attestation"] is False
    assert attestation["open_language_provenance_claim"] == ("source_and_completeness_only")
    compiler = _json(v3_dir / "compiler_contract.json")
    assert compiler["fixture_count"] == 51
    assert compiler["all_passed"] is True
    assert compiler["compiler_generated_expected_results"] is False
    baseline = _json(v3_dir / "baseline_manifest.json")
    assert baseline["parser_conditional_risk"] == 0.0
    assert baseline["held_out_semantic_abstention_count"] == 16
    assert baseline["unsafe_terminal_count"] == 0
    assert baseline["parser_impossibility_claim_forbidden"] is True
    inventory = _json(v3_dir / "source_inventory.json")["files"]
    assert (
        baseline["parser_suite_source_sha256"]
        == inventory["app/eval/q5_frontier_parser_suite_v3.py"]
    )
    headroom = _json(v3_dir / "headroom_preflight.json")
    assert headroom["valid"] is True
    assert headroom["resolvable_deterministic_abstention_count"] == 16
    assert len(headroom["policy_families"]) == 4
    assert len(headroom["semantic_phenomena"]) == 4
    assert all(headroom["checks"].values())
    leakage = _json(v3_dir / "leakage_report.json")
    assert leakage["valid"] is True
    assert leakage["dev_test_disjointness"]["status"] == "not_evaluated"
    assert not Path("data/q5_test").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "true_false_swap",
        "operator_swap",
        "exception_predicate",
        "exception_action",
        "scope_omission",
        "observation_type",
        "cross_trial_span",
        "semantic_self_report",
        "headroom_inflation",
        "graded_rewrite",
        "source_forgery",
        "missing_artifact",
        "extra_artifact",
        "synchronized_policy_fixed",
        "synchronized_state_fixed",
    ],
)
def test_v3_rehashed_mutation_matrix_fails_closed(
    v3_dir: Path, tmp_path: Path, mutation: str
) -> None:
    target = tmp_path / mutation
    shutil.copytree(v3_dir, target)
    if mutation in {
        "true_false_swap",
        "operator_swap",
        "exception_predicate",
        "exception_action",
        "scope_omission",
        "observation_type",
        "cross_trial_span",
    }:
        rows = _jsonl(target / "semantic_candidates.jsonl")
        row = rows[20]
        ir = row["policy_ir"]
        if mutation == "true_false_swap":
            ir["true_disposition"], ir["false_disposition"] = (
                ir["false_disposition"],
                ir["true_disposition"],
            )
        elif mutation == "operator_swap":
            predicate = ir["condition"]["all_of"][0]
            predicate["operator"] = "ne" if predicate["operator"] == "eq" else "eq"
        elif mutation == "exception_predicate":
            ir["exceptions"][0]["predicate"]["value"] = False
        elif mutation == "exception_action":
            ir["exceptions"][0]["disposition"] = "no_action"
        elif mutation == "scope_omission":
            row["closed_bindings"] = [
                item
                for item in row["closed_bindings"]
                if item["field_path"] != "scope.allowed_scopes"
            ]
        elif mutation == "observation_type":
            current = ir["evidence_requirements"]["observation_type"]
            ir["evidence_requirements"]["observation_type"] = (
                "inspect_change_state"
                if current != "inspect_change_state"
                else "inspect_incident_state"
            )
        else:
            row["open_provenance"][0]["policy_spans"] = rows[-1]["open_provenance"][0][
                "policy_spans"
            ]
        _write_jsonl(target / "semantic_candidates.jsonl", rows)
    elif mutation == "semantic_self_report":
        rows = _jsonl(target / "semantic_attestations.jsonl")
        rows[0]["semantic_correctness_source"] = "not_graded"
        rows[0]["semantic_correctness_offline_graded"] = None
        _write_jsonl(target / "semantic_attestations.jsonl", rows)
    elif mutation == "headroom_inflation":
        receipt = _json(target / "headroom_preflight.json")
        receipt["resolvable_deterministic_abstention_count"] = 64
        _write_json(target / "headroom_preflight.json", receipt)
    elif mutation == "graded_rewrite":
        rows = _jsonl(target / "graded_rows.jsonl")
        rows[0]["success"] = not rows[0]["success"]
        _write_jsonl(target / "graded_rows.jsonl", rows)
    elif mutation == "source_forgery":
        inventory = _json(target / "source_inventory.json")
        first = next(iter(inventory["files"]))
        inventory["files"][first] = "0" * 64
        _write_json(target / "source_inventory.json", inventory)
    elif mutation == "missing_artifact":
        (target / "renderer_manifest.json").unlink()
    elif mutation == "extra_artifact":
        (target / "unsealed.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "synchronized_policy_fixed":
        _synchronized_state_mutation(target)
    else:
        _synchronized_policy_mutation(target)
    _rehash(target)
    with pytest.raises((ValueError, ValidationError, KeyError)):
        verify_frontier_v3_artifacts(target)


def test_historical_frontiers_and_boundary_a_still_verify() -> None:
    verify_frontier_artifacts("data/q5_frontier/dev")
    verify_frontier_v2_artifacts("data/q5_frontier/dev-v2")
    boundary = Path("data/eval_runs/q5-boundary-a-k0-ef75a6e")
    kwargs = {
        "v3_run": Path("data/eval_runs/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3"),
        "v3_gold": Path("data/q5/archive/dev-v3/gold.jsonl"),
        "v4_run": Path("data/eval_runs/q5-dev-v4-mock-ir-7a9bf34-primary-k3"),
        "v4_gold": Path("data/q5/dev/gold.jsonl"),
        "value_dir": Path("data/eval_runs/q5-dev-v4-value-ir-7a9bf34-primary-k3"),
        "symbolic_dir": Path("data/eval_runs/q5-dev-v4-symbolic-ir-7a9bf34-primary-k3"),
        "receipt_path": Path("data/eval_runs/q5-dev-v4-preflight-ir-7a9bf34-primary-k3.json"),
        "dataset_root": Path("data/q5/dev"),
    }
    if boundary.exists() and all(path.exists() for path in kwargs.values()):
        verify_boundary_a_evidence(boundary, **kwargs)


def _synchronized_state_mutation(target: Path) -> None:
    topology = _jsonl(target / "topology.jsonl")
    pair_id = next(
        row["pair_id"] for row in topology if row["pair_kind"] == "policy_fixed_state_changed"
    )
    refs = {row["runtime_ref"] for row in topology if row["pair_id"] == pair_id}
    for name, nested in (
        ("runtime_cases.jsonl", False),
        ("environment_authoring.jsonl", True),
    ):
        rows = _jsonl(target / name)
        for row in rows:
            if row["runtime_ref"] in refs:
                payload = row["runtime_payload"] if nested else row
                payload["trusted_observation"]["state"]["scope"] = "staging"
        _write_jsonl(target / name, rows)


def _synchronized_policy_mutation(target: Path) -> None:
    topology = _jsonl(target / "topology.jsonl")
    pair_id = next(
        row["pair_id"] for row in topology if row["pair_kind"] == "state_fixed_policy_changed"
    )
    refs = {row["runtime_ref"] for row in topology if row["pair_id"] == pair_id}
    rows = _jsonl(target / "policy_ir.jsonl")
    for row in rows:
        if row["runtime_ref"] in refs:
            row["policy_ir"]["false_disposition"] = "human_review"
    _write_jsonl(target / "policy_ir.jsonl", rows)


def _rehash(target: Path) -> None:
    hashes = {
        path.name: _sha(path)
        for path in sorted(target.iterdir())
        if path.is_file() and path.name != "frontier_hashes.json"
    }
    _write_json(
        target / "frontier_hashes.json",
        {"schema_version": "q5-frontier-v6-hashes-v3", "artifacts": hashes},
    )


def _rehash_boundary(target: Path) -> None:
    artifacts = {
        name: _sha(target / name)
        for name in (
            "boundary_b_summary.json",
            "boundary_b_report.md",
            "frozen_dev_v2_hashes.json",
            "parser_rows.jsonl",
        )
    }
    _write_json(
        target / "boundary_b_hashes.json",
        {"schema_version": "q5-boundary-b-hashes-v1", "artifacts": artifacts},
    )


def _tree_hashes(path: Path) -> dict[str, str]:
    return {item.name: _sha(item) for item in sorted(path.iterdir()) if item.is_file()}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
