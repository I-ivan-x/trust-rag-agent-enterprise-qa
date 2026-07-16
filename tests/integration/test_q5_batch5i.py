from __future__ import annotations

import copy
import inspect
import json
import shutil
from pathlib import Path

import pytest

from app.eval import q5_symbolic_control as symbolic_module
from app.eval.q5_claim_readiness import evaluate_q5_claim_readiness
from app.eval.q5_dataset import load_q5_environment, load_q5_tasks
from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_provenance import q5_sha256_file, verify_q5_graded_run
from app.eval.q5_runner import (
    Q5_V4_RUNTIME_ATTESTATION,
    Q5RunSettings,
    grade_q5_run,
    load_q5_runtime_cases,
    run_q5_tasks,
)
from app.eval.q5_symbolic_control import (
    Q5StrongSymbolicPolicy,
    build_q5_strong_symbolic_artifacts,
    q5_symbolic_policy_match,
    verify_q5_strong_symbolic_artifacts,
)
from app.eval.q5_value_ledger import build_q5_value_ledger, verify_q5_value_ledger
from app.govern.q5_loop import Q5AgentSystem
from scripts import preflight_q5_i as preflight_i
from tests.integration.test_q5_harness import _refresh_raw_hash

DATASET = Path("data/q5/dev")
GOLD = DATASET / "gold.jsonl"


@pytest.fixture(scope="module")
def q5_i_bundle(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("q5-i-bundle")
    tasks = load_q5_tasks(DATASET / "tasks.jsonl")
    run = run_q5_tasks(
        tasks,
        load_q5_environment(DATASET / "environment.jsonl"),
        list(Q5AgentSystem),
        runtime_cases=load_q5_runtime_cases(DATASET / "runtime_cases.jsonl"),
        settings=Q5RunSettings(
            output_root=root,
            run_id="q5-i-fixture-primary-k3",
            k=3,
            seed=20260715,
            bootstrap_resamples=10_000,
            mode="mock",
            model_role="primary",
        ),
        model_factory=lambda task, system, run_index: Q5DeterministicMockPolicyModel(),
    )
    grade_q5_run(run.run_dir, GOLD)
    value = root / "value"
    symbolic = root / "symbolic"
    build_q5_value_ledger(run.run_dir, GOLD, value)
    build_q5_strong_symbolic_artifacts(
        tasks_path=DATASET / "tasks.jsonl",
        environment_path=DATASET / "environment.jsonl",
        runtime_cases_path=DATASET / "runtime_cases.jsonl",
        gold_path=GOLD,
        output_dir=symbolic,
    )
    return {"run": run.run_dir, "value": value, "symbolic": symbolic, "root": root}


def test_q5_i_cognitive_routing_topology_and_outcomes(q5_i_bundle) -> None:
    run_dir = q5_i_bundle["run"]
    manifest = _json(run_dir / "manifest.json")
    assert manifest["runtime_attestation"] == Q5_V4_RUNTIME_ATTESTATION
    rows = _jsonl(run_dir / "results.jsonl")
    calls = {
        system: sum(row["llm_calls"] for row in rows if row["system"] == system)
        for system in ("q5_rule_agent", "q5_llm_agent", "q5_hybrid_agent")
    }
    assert calls == {
        "q5_rule_agent": 0,
        "q5_llm_agent": 132,
        "q5_hybrid_agent": 42,
    }
    hybrid = [row for row in rows if row["system"] == "q5_hybrid_agent"]
    assert sum(row["llm_calls"] > 0 for row in hybrid) == 39
    policy = _jsonl(run_dir / "policy_events.jsonl")
    assert sum(
        event["llm_called"]
        for event in policy
        if event["system"] == "q5_hybrid_agent"
        and event["accepted_proposal"]["kind"] == "observe"
    ) == 3
    summary = _json(run_dir / "summary.json")
    hybrid_metrics = summary["by_system"]["q5_hybrid_agent"]
    assert hybrid_metrics["required_observation_recall"] == 1.0
    assert hybrid_metrics["duplicate_successful_observation_count"] == 0
    assert hybrid_metrics["post_observation_terminal_rate"] == 1.0
    assert hybrid_metrics["policy_disposition_action_consistency"] == 1.0


@pytest.mark.parametrize("mutation", ["delete", "replace", "downgrade"])
def test_q5_i_runtime_attestation_mutations_fail_closed(
    q5_i_bundle,
    tmp_path: Path,
    mutation: str,
) -> None:
    source = q5_i_bundle["run"]
    target = tmp_path / mutation
    _copy_raw_artifacts(source, target)
    manifest = _json(target / "manifest.json")
    if mutation == "delete":
        del manifest["runtime_attestation"]
    elif mutation == "replace":
        manifest["runtime_attestation"]["cognitive_step_routing"] = "forged"
    else:
        manifest["runtime_attestation"] = {
            "schema_version": "q5-runtime-attestation-hr3",
            "trusted_policy_block": "same_trial_route_fact_v1",
            "timeout_recovery": "bounded_policy_replan_v1",
        }
    _write_json(target / "manifest.json", manifest)
    _refresh_raw_hash(target, "manifest.json")
    with pytest.raises(ValueError):
        grade_q5_run(target, GOLD)


@pytest.mark.parametrize(
    ("artifact", "mutation"),
    [
        ("value_ledger.jsonl", "missing"),
        ("value_ledger.jsonl", "duplicate"),
        ("value_ledger.jsonl", "extra"),
        ("value_ledger.jsonl", "phase"),
        ("value_summary.json", "source_hash"),
    ],
)
def test_q5_value_ledger_rehashed_mutations_fail_closed(
    q5_i_bundle,
    tmp_path: Path,
    artifact: str,
    mutation: str,
) -> None:
    target = tmp_path / mutation
    shutil.copytree(q5_i_bundle["value"], target)
    path = target / artifact
    if artifact.endswith(".jsonl"):
        rows = _jsonl(path)
        if mutation == "missing":
            rows.pop()
        elif mutation == "duplicate":
            rows[-1] = copy.deepcopy(rows[0])
        elif mutation == "extra":
            rows.append(copy.deepcopy(rows[0]))
        else:
            rows[0]["terminal_binding_llm_calls"] += 1
        _write_jsonl(path, rows)
    else:
        payload = _json(path)
        payload["source_hashes"]["trajectory.jsonl"] = "0" * 64
        _write_json(path, payload)
    hashes = _json(target / "value_hashes.json")
    hashes["artifacts"][artifact] = q5_sha256_file(path)
    _write_json(target / "value_hashes.json", hashes)
    with pytest.raises(ValueError):
        verify_q5_value_ledger(q5_i_bundle["run"], GOLD, target)


def test_q5_symbolic_control_is_zero_call_hash_closed_and_identity_free(
    q5_i_bundle,
) -> None:
    summary = verify_q5_strong_symbolic_artifacts(
        tasks_path=DATASET / "tasks.jsonl",
        environment_path=DATASET / "environment.jsonl",
        runtime_cases_path=DATASET / "runtime_cases.jsonl",
        gold_path=GOLD,
        output_dir=q5_i_bundle["symbolic"],
    )
    assert summary["semantic_success"] == 1.0
    assert summary["within_policy_pair_success"] == 1.0
    assert summary["cross_policy_pair_success"] == 1.0
    assert summary["llm_calls"] == summary["total_tokens"] == 0
    assert summary["source_file_sha256"] == summary["source_dependency_sha256"][
        "app/eval/q5_symbolic_control.py"
    ]
    assert len(summary["source_dependency_sha256"]) >= 9
    assert summary["control_kind"] == "frozen_closed_vocabulary_parser"
    assert "not_general_natural_language_rule_solving" in summary["claim_scope"]
    lowered = inspect.getsource(Q5StrongSymbolicPolicy).lower()
    for forbidden in ("case_id", "gold_reason", "stratum", "pair_tag", "expected_action"):
        assert forbidden not in lowered


def test_q5_symbolic_rehashed_row_mutation_fails_closed(
    q5_i_bundle,
    tmp_path: Path,
) -> None:
    target = tmp_path / "symbolic"
    shutil.copytree(q5_i_bundle["symbolic"], target)
    rows = _jsonl(target / "symbolic_rows.jsonl")
    rows[0]["trajectory_qualified_success"] = not rows[0][
        "trajectory_qualified_success"
    ]
    _write_jsonl(target / "symbolic_rows.jsonl", rows)
    hashes = _json(target / "symbolic_hashes.json")
    hashes["artifacts"]["symbolic_rows.jsonl"] = q5_sha256_file(
        target / "symbolic_rows.jsonl"
    )
    _write_json(target / "symbolic_hashes.json", hashes)
    with pytest.raises(ValueError):
        verify_q5_strong_symbolic_artifacts(
            tasks_path=DATASET / "tasks.jsonl",
            environment_path=DATASET / "environment.jsonl",
            runtime_cases_path=DATASET / "runtime_cases.jsonl",
            gold_path=GOLD,
            output_dir=target,
        )


def test_q5_symbolic_policy_match_is_identity_and_order_invariant() -> None:
    first = (
        "resource:alpha is governed by change:one. A completed replacement "
        "makes the runbook stale; a planned replacement requires human review."
    )
    transformed = (
        "An unrelated clause describes documentation only. "
        "A planned replacement requires human review; resource:renamed is "
        "governed by change:renamed. A completed replacement makes the runbook stale."
    )
    kwargs = {
        "status": "completed",
        "observed_scope": None,
        "requested_scope": None,
    }
    assert q5_symbolic_policy_match(first, **kwargs) == "mark_stale"
    assert q5_symbolic_policy_match(transformed, **kwargs) == "mark_stale"


def test_q5_claim_readiness_fail_closed_on_symbolic_headroom(q5_i_bundle) -> None:
    run_summary = _json(q5_i_bundle["run"] / "summary.json")
    value = verify_q5_value_ledger(q5_i_bundle["run"], GOLD, q5_i_bundle["value"])
    symbolic = _json(q5_i_bundle["symbolic"] / "symbolic_summary.json")
    readiness = evaluate_q5_claim_readiness(run_summary, value, symbolic)
    assert readiness["valid"] is False
    assert "claim_headroom" in readiness["blockers"]
    assert "beneficial_evidence_absent" in readiness["blockers"]
    assert readiness["checks"]["semantic_headroom"] is False
    assert readiness["checks"]["beneficial_value_capture"] is None


def test_q5_value_ledger_is_complete_case_system_run_matrix(q5_i_bundle) -> None:
    rows = _jsonl(q5_i_bundle["value"] / "value_ledger.jsonl")
    assert len(rows) == 324
    assert len(
        {(row["case_id"], row["system"], row["run_index"]) for row in rows}
    ) == 324
    summary = _json(q5_i_bundle["value"] / "value_summary.json")
    assert summary["beneficial_group_count"] == 0
    assert summary["beneficial_capture_numerator"] == 0
    assert summary["beneficial_capture_denominator"] == 0
    assert summary["beneficial_capture_vacuous"] is True
    assert summary["beneficial_value_capture"] is None
    assert (
        summary["hybrid_observation_planning_llm_calls_global"],
        summary["hybrid_observation_planning_llm_calls_semantic"],
        summary["hybrid_observation_planning_llm_calls_adversarial"],
    ) == (3, 0, 3)
    assert (
        summary["hybrid_terminal_binding_llm_calls_global"],
        summary["hybrid_terminal_binding_llm_calls_semantic"],
        summary["hybrid_terminal_binding_llm_calls_adversarial"],
    ) == (39, 36, 3)


@pytest.mark.parametrize(
    ("field", "mutated"),
    [
        ("beneficial_value_capture", 1.0),
        ("beneficial_group_count", 1),
        ("beneficial_capture_numerator", 1),
        ("beneficial_capture_denominator", 1),
        ("hybrid_observation_planning_llm_calls_global", 0),
        ("hybrid_observation_planning_llm_calls_semantic", 3),
    ],
)
def test_q5_value_v2_summary_mutations_fail_closed(
    q5_i_bundle,
    tmp_path: Path,
    field: str,
    mutated: object,
) -> None:
    target = tmp_path / field
    shutil.copytree(q5_i_bundle["value"], target)
    summary_path = target / "value_summary.json"
    summary = _json(summary_path)
    summary[field] = mutated
    _write_json(summary_path, summary)
    _rehash_sidecar_artifact(target, "value", "value_summary.json")
    with pytest.raises(ValueError):
        verify_q5_value_ledger(q5_i_bundle["run"], GOLD, target)


def test_q5_value_v2_scoped_global_phase_swap_fails_closed(
    q5_i_bundle,
    tmp_path: Path,
) -> None:
    target = tmp_path / "phase-swap"
    shutil.copytree(q5_i_bundle["value"], target)
    summary_path = target / "value_summary.json"
    summary = _json(summary_path)
    global_calls = summary["hybrid_observation_planning_llm_calls_global"]
    semantic_calls = summary["hybrid_observation_planning_llm_calls_semantic"]
    summary["hybrid_observation_planning_llm_calls_global"] = semantic_calls
    summary["hybrid_observation_planning_llm_calls_semantic"] = global_calls
    _write_json(summary_path, summary)
    _rehash_sidecar_artifact(target, "value", "value_summary.json")
    with pytest.raises(ValueError):
        verify_q5_value_ledger(q5_i_bundle["run"], GOLD, target)


@pytest.mark.parametrize("sidecar", ["value", "symbolic"])
def test_q5_sidecar_v2_downgrade_to_v1_fails_closed(
    q5_i_bundle,
    tmp_path: Path,
    sidecar: str,
) -> None:
    target = tmp_path / sidecar
    shutil.copytree(q5_i_bundle[sidecar], target)
    hashes_path = target / f"{sidecar}_hashes.json"
    hashes = _json(hashes_path)
    hashes["schema_version"] = (
        "q5-value-hashes-v1"
        if sidecar == "value"
        else "q5-strong-symbolic-hashes-v1"
    )
    _write_json(hashes_path, hashes)
    with pytest.raises(ValueError):
        if sidecar == "value":
            verify_q5_value_ledger(q5_i_bundle["run"], GOLD, target)
        else:
            _verify_symbolic(target)


def test_q5_symbolic_v2_dependency_inventory_mutation_fails_closed(
    q5_i_bundle,
    tmp_path: Path,
) -> None:
    target = tmp_path / "symbolic"
    shutil.copytree(q5_i_bundle["symbolic"], target)
    summary_path = target / "symbolic_summary.json"
    summary = _json(summary_path)
    summary["source_dependency_sha256"]["app/govern/q5_tools.py"] = "0" * 64
    _write_json(summary_path, summary)
    _rehash_sidecar_artifact(target, "symbolic", "symbolic_summary.json")
    with pytest.raises(ValueError):
        _verify_symbolic(target)


def test_q5_symbolic_v2_omitted_helper_change_invalidates_old_attestation(
    q5_i_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = symbolic_module._source_inventory()
    changed = dict(original)
    changed["app/eval/q5_symbolic_control.py"] = "f" * 64
    monkeypatch.setattr(symbolic_module, "_source_inventory", lambda: changed)
    with pytest.raises(ValueError):
        _verify_symbolic(q5_i_bundle["symbolic"])


@pytest.mark.parametrize(
    "mutation",
    [
        "value_capture",
        "value_count",
        "value_numerator",
        "value_denominator",
        "value_phase_swap",
        "value_downgrade",
        "symbolic_source",
        "symbolic_downgrade",
    ],
)
def test_q5_ir_preflight_rejects_rehashed_sidecar_mutations(
    q5_i_bundle,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    value = q5_i_bundle["value"]
    symbolic = q5_i_bundle["symbolic"]
    sidecar = "value" if mutation.startswith("value_") else "symbolic"
    target = tmp_path / sidecar
    shutil.copytree(q5_i_bundle[sidecar], target)
    if sidecar == "value":
        if mutation == "value_downgrade":
            hashes_path = target / "value_hashes.json"
            hashes = _json(hashes_path)
            hashes["schema_version"] = "q5-value-hashes-v1"
            _write_json(hashes_path, hashes)
        else:
            summary_path = target / "value_summary.json"
            summary = _json(summary_path)
            if mutation == "value_capture":
                summary["beneficial_value_capture"] = 1.0
            elif mutation == "value_count":
                summary["beneficial_group_count"] = 1
            elif mutation == "value_numerator":
                summary["beneficial_capture_numerator"] = 1
            elif mutation == "value_denominator":
                summary["beneficial_capture_denominator"] = 1
            else:
                global_calls = summary[
                    "hybrid_observation_planning_llm_calls_global"
                ]
                semantic_calls = summary[
                    "hybrid_observation_planning_llm_calls_semantic"
                ]
                summary["hybrid_observation_planning_llm_calls_global"] = (
                    semantic_calls
                )
                summary["hybrid_observation_planning_llm_calls_semantic"] = (
                    global_calls
                )
            _write_json(summary_path, summary)
            _rehash_sidecar_artifact(target, "value", "value_summary.json")
        value = target
    else:
        if mutation == "symbolic_downgrade":
            hashes_path = target / "symbolic_hashes.json"
            hashes = _json(hashes_path)
            hashes["schema_version"] = "q5-strong-symbolic-hashes-v1"
            _write_json(hashes_path, hashes)
        else:
            summary_path = target / "symbolic_summary.json"
            summary = _json(summary_path)
            summary["source_file_sha256"] = "0" * 64
            _write_json(summary_path, summary)
            _rehash_sidecar_artifact(target, "symbolic", "symbolic_summary.json")
        symbolic = target
    monkeypatch.setattr(
        preflight_i,
        "run_base_preflight",
        lambda argv: {
            "schema_version": "q5-real-preflight-v4",
            "valid": True,
            "request_policy": {
                "completion_requests_sent_during_preflight": 0,
                "http_model_requests_sent_during_preflight": 0,
                "provider_model_calls_during_preflight": 0,
            },
            "errors": [],
        },
    )
    with pytest.raises(ValueError):
        preflight_i.main(
            [
                "--mock-run",
                str(q5_i_bundle["run"]),
                "--value-dir",
                str(value),
                "--symbolic-dir",
                str(symbolic),
                "--output",
                str(tmp_path / "receipt.json"),
                "--real-run-id",
                "q5-ir-never-executed",
            ]
        )


def test_q5_ir_preflight_rejects_omitted_helper_change(
    q5_i_bundle,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = symbolic_module._source_inventory()
    changed = dict(original)
    changed["app/eval/q5_symbolic_control.py"] = "f" * 64
    monkeypatch.setattr(symbolic_module, "_source_inventory", lambda: changed)
    monkeypatch.setattr(
        preflight_i,
        "run_base_preflight",
        lambda argv: {
            "schema_version": "q5-real-preflight-v4",
            "valid": True,
            "request_policy": {
                "completion_requests_sent_during_preflight": 0,
                "http_model_requests_sent_during_preflight": 0,
                "provider_model_calls_during_preflight": 0,
            },
            "errors": [],
        },
    )
    with pytest.raises(ValueError):
        preflight_i.main(
            [
                "--mock-run",
                str(q5_i_bundle["run"]),
                "--value-dir",
                str(q5_i_bundle["value"]),
                "--symbolic-dir",
                str(q5_i_bundle["symbolic"]),
                "--output",
                str(tmp_path / "receipt.json"),
                "--real-run-id",
                "q5-ir-never-executed",
            ]
        )


@pytest.mark.skipif(
    not Path("data/eval_runs/q5-dev-v4-value-i-73c9b34-primary-k3").exists(),
    reason="local frozen 5-I sidecars are absent",
)
def test_q5_frozen_v1_sidecars_still_verify() -> None:
    run = Path("data/eval_runs/q5-dev-v4-mock-i-73c9b34-primary-k3")
    value = verify_q5_value_ledger(
        run,
        GOLD,
        "data/eval_runs/q5-dev-v4-value-i-73c9b34-primary-k3",
    )
    symbolic = _verify_symbolic(
        Path("data/eval_runs/q5-dev-v4-symbolic-i-73c9b34-primary-k3")
    )
    assert value["schema_version"] == "q5-value-summary-v1"
    assert symbolic["schema_version"] == "q5-strong-symbolic-summary-v1"


def test_q5_i_bundle_reverifies(q5_i_bundle) -> None:
    verified = verify_q5_graded_run(q5_i_bundle["run"], GOLD)
    assert verified.protocol_version == "v4"


def _copy_raw_artifacts(source: Path, target: Path) -> None:
    target.mkdir()
    raw_files = set(_json(source / "hashes.json")["artifacts"]) | {"hashes.json"}
    for name in raw_files:
        shutil.copy2(source / name, target / name)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _rehash_sidecar_artifact(target: Path, sidecar: str, artifact: str) -> None:
    hashes_path = target / f"{sidecar}_hashes.json"
    hashes = _json(hashes_path)
    hashes["artifacts"][artifact] = q5_sha256_file(target / artifact)
    _write_json(hashes_path, hashes)


def _verify_symbolic(path: Path) -> dict:
    return verify_q5_strong_symbolic_artifacts(
        tasks_path=DATASET / "tasks.jsonl",
        environment_path=DATASET / "environment.jsonl",
        runtime_cases_path=DATASET / "runtime_cases.jsonl",
        gold_path=GOLD,
        output_dir=path,
    )
