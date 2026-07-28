from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_boundary_a import verify_boundary_a_evidence
from app.eval.q5_frontier_v2 import (
    FRONTIER_V2_FILES,
    grade_frontier_execution,
    verify_frontier_v2_artifacts,
    write_frontier_v2_artifacts,
)


@pytest.fixture()
def frontier_v2_dir(tmp_path: Path) -> Path:
    target = tmp_path / "dev-v2"
    write_frontier_v2_artifacts(target)
    return target


def test_k0r_v2_artifacts_boundary_coverage_and_leakage(
    frontier_v2_dir: Path,
) -> None:
    manifest = verify_frontier_v2_artifacts(frontier_v2_dir)
    assert {item.name for item in frontier_v2_dir.iterdir()} == FRONTIER_V2_FILES
    assert manifest["case_count"] == 48
    assert manifest["execution_boundary"] == {
        "input_artifacts": ["runtime_cases.jsonl"],
        "forbidden_execution_inputs": [
            "policy_ir.jsonl",
            "gold.jsonl",
            "environment_authoring.jsonl",
            "topology.jsonl",
            "rendered_meaning.jsonl",
        ],
        "execution_rows_label_free": True,
        "execution_row_count": 192,
    }
    coverage = manifest["ir_coverage_matrix"]
    assert set(coverage["predicate_operator_counts"]) == {"eq", "ne", "in"}
    assert coverage["all_of_case_count"] > 0
    assert coverage["any_of_case_count"] > 0
    assert coverage["exception_active_count"] > 0
    assert coverage["exception_inactive_count"] > 0
    assert len(coverage["precedence_counts"]) >= 3
    assert coverage["scope_match_count"] > 0
    assert coverage["scope_mismatch_count"] > 0
    assert coverage["observation_failure_count"] > 0
    assert coverage["unauthorized_count"] > 0
    assert manifest["pair_audit"] == {
        "pair_count": 24,
        "policy_fixed_state_changed_pair_count": 12,
        "state_fixed_policy_changed_pair_count": 12,
        "policy_fixed_invariants_valid": True,
        "state_fixed_invariants_valid": True,
    }
    baseline = _json(frontier_v2_dir / "baseline_manifest.json")
    assert baseline["acceptance"] == {
        "policy_ir_oracle_success_count": 48,
        "policy_ir_oracle_case_count": 48,
        "symbolic_complete_parser_coverage": 1.0,
        "symbolic_complete_wrong_execution_count": 0,
        "ambiguous_or_unsafe_unsafe_terminal_count": 0,
    }
    semantic = baseline["baseline_summaries"]["generic_clause_parser"][
        "semantic_open"
    ]
    assert semantic["must_fail_threshold"] is None
    assert 0 < semantic["parser_coverage"] < 1
    prereg = _json(frontier_v2_dir / "claim_preregistration.json")
    thresholds = prereg["headline_thresholds"]
    assert thresholds["beneficial_distinct_case_min"] >= 4
    assert thresholds["beneficial_policy_family_min"] >= 2
    assert thresholds["beneficial_semantic_phenomenon_min"] >= 2
    for required in (
        "llm_uplift_on_parser_abstained_subset_min",
        "parser_conditional_risk_max",
        "beneficial_capture_min",
        "harmful_exposure_max",
        "hybrid_oracle_regret_max",
        "call_avoidance_min",
        "token_avoidance_min",
        "family_success_min",
        "counterfactual_pair_success_min",
        "unsafe_action_max",
        "invalid_transition_max",
        "schema_failure_max",
    ):
        assert required in thresholds
    leakage = _json(frontier_v2_dir / "leakage_report.json")
    assert leakage["valid"] is True
    assert leakage["action_label_exposure"]["outside_policy_and_legal_surface"] == []
    assert leakage["unique_text_template_multiplicity"][
        "unique_policy_text_count"
    ] > 1
    assert leakage["renderer_coverage"]
    assert leakage["dev_test_renderer_disjointness"]["status"] == "not_evaluated"
    assert not Path("data/q5_frontier/test").exists()
    assert not Path("data/q5_test").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_execution",
        "duplicate_execution",
        "extra_execution",
        "execution_label",
        "cross_case_ir",
        "runtime_gold",
        "unauthorized_chunk",
        "source_hash",
        "renderer_boundary",
        "self_report",
        "synchronized_policy_fixed",
        "synchronized_state_fixed",
    ],
)
def test_k0r_rehashed_mutation_matrix_fails_closed(
    frontier_v2_dir: Path, tmp_path: Path, mutation: str
) -> None:
    target = tmp_path / mutation
    shutil.copytree(frontier_v2_dir, target)
    if mutation in {"missing_execution", "duplicate_execution", "extra_execution"}:
        rows = _jsonl(target / "execution_rows.jsonl")
        if mutation == "missing_execution":
            rows.pop()
        elif mutation == "duplicate_execution":
            rows.append(rows[0])
        else:
            rows.append({**rows[0], "runtime_ref": "frontier-v2-resource:r999"})
        _write_jsonl(target / "execution_rows.jsonl", rows)
    elif mutation == "execution_label":
        rows = _jsonl(target / "execution_rows.jsonl")
        rows[0]["gold_disposition"] = "remediate"
        _write_jsonl(target / "execution_rows.jsonl", rows)
    elif mutation == "cross_case_ir":
        rows = _jsonl(target / "policy_ir.jsonl")
        donor = next(row for row in rows[1:] if row["policy_ir"] != rows[0]["policy_ir"])
        rows[0]["policy_ir"] = donor["policy_ir"]
        _write_jsonl(target / "policy_ir.jsonl", rows)
    elif mutation == "runtime_gold":
        rows = _jsonl(target / "runtime_cases.jsonl")
        rows[0]["gold"] = "remediate"
        _write_jsonl(target / "runtime_cases.jsonl", rows)
    elif mutation == "unauthorized_chunk":
        rows = _jsonl(target / "runtime_cases.jsonl")
        row = next(
            item
            for item in rows
            if not item["trusted_observation"]["authorization"]["authorized"]
        )
        row["trusted_observation"]["authorization"][
            "authorized_evidence_ids"
        ] = ["chunk:forged"]
        _write_jsonl(target / "runtime_cases.jsonl", rows)
    elif mutation == "source_hash":
        manifest = _json(target / "policy_ir_manifest.json")
        manifest["source_sha256"]["app/eval/q5_frontier_v2.py"] = "0" * 64
        _write_json(target / "policy_ir_manifest.json", manifest)
    elif mutation == "renderer_boundary":
        manifest = _json(target / "renderer_manifest.json")
        manifest["semantic_boundary_uses_renderer_prefix"] = True
        _write_json(target / "renderer_manifest.json", manifest)
    elif mutation == "self_report":
        prereg = _json(target / "claim_preregistration.json")
        prereg["readiness"] = "valid"
        _write_json(target / "claim_preregistration.json", prereg)
    elif mutation == "synchronized_policy_fixed":
        _mutate_synchronized_policy_fixed(target)
    else:
        _mutate_synchronized_state_fixed(target)
    _rehash(target)
    with pytest.raises((ValueError, KeyError)):
        verify_frontier_v2_artifacts(target)


def test_offline_grader_requires_exact_trial_matrix_and_sealed_gold(
    frontier_v2_dir: Path,
) -> None:
    kwargs = {
        "execution_rows": _jsonl(frontier_v2_dir / "execution_rows.jsonl"),
        "policy_ir_rows": _jsonl(frontier_v2_dir / "policy_ir.jsonl"),
        "environment_authoring_rows": _jsonl(
            frontier_v2_dir / "environment_authoring.jsonl"
        ),
        "gold_rows": _jsonl(frontier_v2_dir / "gold.jsonl"),
        "topology_rows": _jsonl(frontier_v2_dir / "topology.jsonl"),
        "rendered_meaning_rows": _jsonl(
            frontier_v2_dir / "rendered_meaning.jsonl"
        ),
    }
    for operation in ("missing", "duplicate", "extra"):
        mutated = json.loads(json.dumps(kwargs))
        if operation == "missing":
            mutated["execution_rows"].pop()
        elif operation == "duplicate":
            mutated["execution_rows"].append(mutated["execution_rows"][0])
        else:
            mutated["execution_rows"].append(
                {
                    **mutated["execution_rows"][0],
                    "runtime_ref": "frontier-v2-resource:r999",
                }
            )
        with pytest.raises(ValueError):
            grade_frontier_execution(**mutated)
    forged = json.loads(json.dumps(kwargs))
    forged["gold_rows"][0]["disposition"] = "human_review"
    with pytest.raises(ValueError, match="sealed Gold"):
        grade_frontier_execution(**forged)


def test_boundary_a_package_remains_byte_identical_and_verifiable() -> None:
    boundary = Path("data/eval_runs/q5-boundary-a-k0-ef75a6e")
    if not boundary.exists():
        pytest.skip("local Boundary A evidence package is absent")
    before = {item.name: _sha(item) for item in boundary.iterdir() if item.is_file()}
    kwargs = {
        "v3_run": Path(
            "data/eval_runs/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3"
        ),
        "v3_gold": Path("data/q5/archive/dev-v3/gold.jsonl"),
        "v4_run": Path("data/eval_runs/q5-dev-v4-mock-ir-7a9bf34-primary-k3"),
        "v4_gold": Path("data/q5/dev/gold.jsonl"),
        "value_dir": Path("data/eval_runs/q5-dev-v4-value-ir-7a9bf34-primary-k3"),
        "symbolic_dir": Path(
            "data/eval_runs/q5-dev-v4-symbolic-ir-7a9bf34-primary-k3"
        ),
        "receipt_path": Path(
            "data/eval_runs/q5-dev-v4-preflight-ir-7a9bf34-primary-k3.json"
        ),
        "dataset_root": Path("data/q5/dev"),
    }
    if any(not path.exists() for path in kwargs.values()):
        pytest.skip("local Boundary A source artifacts are absent")
    verify_boundary_a_evidence(boundary, **kwargs)
    after = {item.name: _sha(item) for item in boundary.iterdir() if item.is_file()}
    assert after == before


def _mutate_synchronized_policy_fixed(target: Path) -> None:
    topology = _jsonl(target / "topology.jsonl")
    pair_id = next(
        row["pair_id"]
        for row in topology
        if row["pair_kind"] == "policy_fixed_state_changed"
    )
    refs = {row["runtime_ref"] for row in topology if row["pair_id"] == pair_id}
    ir_rows = _jsonl(target / "policy_ir.jsonl")
    for row in ir_rows:
        if row["runtime_ref"] in refs:
            row["policy_ir"]["condition"]["all_of"][0]["value"] = "forged"
    _write_jsonl(target / "policy_ir.jsonl", ir_rows)
    runtime_rows = _jsonl(target / "runtime_cases.jsonl")
    environment_rows = _jsonl(target / "environment_authoring.jsonl")
    for row in runtime_rows:
        if row["runtime_ref"] in refs:
            row["policy_text"] = row["policy_text"].replace("outage", "forged")
    for row in environment_rows:
        if row["runtime_ref"] in refs:
            payload = row["runtime_payload"]
            payload["policy_text"] = payload["policy_text"].replace(
                "outage", "forged"
            )
    _write_jsonl(target / "runtime_cases.jsonl", runtime_rows)
    _write_jsonl(target / "environment_authoring.jsonl", environment_rows)


def _mutate_synchronized_state_fixed(target: Path) -> None:
    topology = _jsonl(target / "topology.jsonl")
    pair_id = next(
        row["pair_id"]
        for row in topology
        if row["pair_kind"] == "state_fixed_policy_changed"
    )
    refs = {row["runtime_ref"] for row in topology if row["pair_id"] == pair_id}
    runtime_rows = _jsonl(target / "runtime_cases.jsonl")
    environment_rows = _jsonl(target / "environment_authoring.jsonl")
    for row in runtime_rows:
        if row["runtime_ref"] in refs:
            row["trusted_observation"]["state"]["scope"] = "forged"
    for row in environment_rows:
        if row["runtime_ref"] in refs:
            row["runtime_payload"]["trusted_observation"]["state"][
                "scope"
            ] = "forged"
    _write_jsonl(target / "runtime_cases.jsonl", runtime_rows)
    _write_jsonl(target / "environment_authoring.jsonl", environment_rows)


def _rehash(target: Path) -> None:
    manifest_path = target / "frontier_dataset_manifest.json"
    manifest = _json(manifest_path)
    for name in manifest["row_sha256"]:
        manifest["row_sha256"][name] = _sha(target / name)
    _write_json(manifest_path, manifest)
    policy_manifest_path = target / "policy_ir_manifest.json"
    policy_manifest = _json(policy_manifest_path)
    policy_manifest["policy_ir_sha256"] = _sha(target / "policy_ir.jsonl")
    _write_json(policy_manifest_path, policy_manifest)
    artifacts = {
        path.name: _sha(path)
        for path in sorted(target.iterdir())
        if path.is_file() and path.name != "frontier_hashes.json"
    }
    _write_json(
        target / "frontier_hashes.json",
        {"schema_version": "q5-frontier-v5-hashes-v2", "artifacts": artifacts},
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
