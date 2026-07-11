from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from app.core.enums import CorpusSource, SourceOrigin
from app.eval.q5_dataset import load_q5_environment, load_q5_tasks
from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_provenance import verify_q5_graded_run
from app.eval.q5_runner import (
    Q5RunSettings,
    Q5RuntimeCaseInput,
    grade_q5_run,
    run_q5_tasks,
)
from app.eval.q5_summary import summarize_q5_model_roles, verify_q5_dual_summary
from app.govern.conditions import ConditionReport, OpsCondition
from app.govern.q5_loop import Q5AgentSystem
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.schemas.q5_task import Q5_GOLD_ONLY_FIELDS, Q5TaskInput
from app.workflow.state import RetrievalPassResult
from scripts.grade_q5_run import main as grade_q5_cli
from scripts.run_q5_tasks import main as run_q5_cli
from tests.helpers import make_retrieved_chunk

FIXTURE_ROOT = Path("tests/fixtures/q5_p4")
TASKS_PATH = FIXTURE_ROOT / "tasks.jsonl"
ENVIRONMENT_PATH = FIXTURE_ROOT / "environment.jsonl"
GOLD_PATH = FIXTURE_ROOT / "gold.jsonl"
RESTRICTED_CANARY = "Q5_P4_RESTRICTED_CANARY_MUST_INVALIDATE_RUN"


class RestrictedEchoModel(Q5DeterministicMockPolicyModel):
    def generate(self, prompt: str) -> str:
        return json.dumps(
            {
                "kind": "terminal",
                "tool": None,
                "args": {},
                "action": "flag_stale",
                "evidence_chunk_ids": ["chunk-q5-p4-committed"],
                "reason_code": "malicious_echo",
                "reason_summary": RESTRICTED_CANARY,
            }
        )


class SpoofRealModel:
    provider = "openai"
    model_name = "spoofed-real-model"
    mock_used = False

    def __init__(self) -> None:
        self.generate_calls = 0
        self.metadata_calls = 0

    def provider_metadata(self) -> dict[str, object]:
        self.metadata_calls += 1
        return {"llm_provider": "openai", "is_mock_llm": False}

    def generate(self, prompt: str) -> str:
        self.generate_calls += 1
        return prompt


class AlternateMockPolicyModel(Q5DeterministicMockPolicyModel):
    provider = "deterministic_mock_alternate"
    model_name = "q5-runtime-policy-v2"


class SameProviderAlternateMockPolicyModel(Q5DeterministicMockPolicyModel):
    model_name = "q5-runtime-policy-v2"


def test_q5_synthetic_mock_harness_runs_and_grades_all_three_systems(
    tmp_path: Path,
) -> None:
    assert "gold" not in inspect.signature(run_q5_tasks).parameters
    assert tuple(inspect.signature(grade_q5_run).parameters) == (
        "run_dir",
        "gold_path",
    )
    tasks = load_q5_tasks(TASKS_PATH)
    environment = load_q5_environment(ENVIRONMENT_PATH)
    before_store = {
        key: environment[key].model_dump(mode="json") for key in environment
    }
    settings = Q5RunSettings(
        output_root=tmp_path,
        run_id="q5-p4-synthetic",
        k=3,
        seed=314159,
        bootstrap_resamples=10_000,
        mode="mock",
        model_role="primary",
    )
    raw = run_q5_tasks(
        tasks,
        environment,
        list(Q5AgentSystem),
        runtime_cases=_runtime_cases(tasks),
        settings=settings,
        model_factory=lambda task, system, run_index: Q5DeterministicMockPolicyModel(),
    )

    assert raw.trial_count == len(tasks) * len(Q5AgentSystem) * settings.k == 45
    assert before_store == {
        key: environment[key].model_dump(mode="json") for key in environment
    }
    expected_raw = {
        "environment_before.json",
        "environment_after.json",
        "tool_events.jsonl",
        "policy_events.jsonl",
        "terminal_events.jsonl",
        "trajectory.jsonl",
        "otel_spans.jsonl",
        "results.jsonl",
        "manifest.json",
        "hashes.json",
    }
    assert expected_raw.issubset({path.name for path in raw.run_dir.iterdir()})

    raw_rows = _jsonl(raw.results_path)
    _assert_no_gold_keys(raw_rows)
    manifest = _json(raw.manifest_path)
    _assert_no_gold_keys(manifest)
    assert set(manifest["dataset_hashes"]) == {
        "tasks",
        "environment",
        "runtime_inputs",
    }
    assert all(len(value) == 64 for value in manifest["dataset_hashes"].values())
    assert len(manifest["prompt"]["sha256"]) == 64
    assert len(manifest["git_commit_sha"]) == 40
    assert manifest["systems"] == [system.value for system in Q5AgentSystem]
    assert manifest["bootstrap"] == {
        "confidence": 0.95,
        "method": "case_id_paired_percentile",
        "resamples": 10_000,
        "seed": 314159,
    }
    assert manifest["mock_used"] is True
    assert manifest["real_run"] is False
    assert manifest["usage"]["llm_calls"] > 0
    assert manifest["usage"]["successful_llm_calls"] == manifest["usage"][
        "llm_calls"
    ]
    assert manifest["model"]["identities"][0]["identity_kind"] == "known_mock"
    assert manifest["model"]["call_evidence"][0]["successful_responses"] > 0
    assert manifest["usage"]["total_tokens"] > 0
    assert manifest["usage"]["cost_usd"] == 0.0
    assert manifest["usage"]["latency_ms"] >= 0.0
    raw_hashes = _json(raw.hashes_path)["artifacts"]
    assert set(raw_hashes) == expected_raw - {"hashes.json"}
    assert all(len(value) == 64 for value in raw_hashes.values())

    before_rows = _indexed_environments(raw.run_dir / "environment_before.json")
    after_rows = _indexed_environments(raw.run_dir / "environment_after.json")
    for system in Q5AgentSystem:
        for run_index in (1, 2, 3):
            committed = _key("q5-p4-committed", system.value, run_index)
            pending = _key("q5-p4-pending", system.value, run_index)
            escalated = _key("q5-p4-escalated", system.value, run_index)
            no_op = _key("q5-p4-noop", system.value, run_index)
            unauthorized = _key("q5-p4-unauthorized", system.value, run_index)
            assert after_rows[committed]["records"][0]["action"] == "flag_stale"
            assert after_rows[committed]["pending_queue"] == []
            assert after_rows[pending]["records"] == []
            assert after_rows[pending]["pending_queue"][0]["action"] == (
                "open_remediation_ticket"
            )
            for unchanged in (escalated, no_op, unauthorized):
                assert after_rows[unchanged]["records"] == before_rows[unchanged]["records"]
                assert after_rows[unchanged]["pending_queue"] == (
                    before_rows[unchanged]["pending_queue"]
                )

    policy_events = _jsonl(raw.run_dir / "policy_events.jsonl")
    assert policy_events
    assert all(event["parse_status"] == "accepted" for event in policy_events)
    assert all("raw_payload" not in event for event in policy_events)
    assert all(
        event["accepted_proposal"] is not None for event in policy_events
    )

    graded = grade_q5_run(raw.run_dir, GOLD_PATH)
    summary = _json(graded.summary_path)
    gates = _json(graded.gates_path)
    graded_manifest = _json(graded.graded_manifest_path)

    assert graded.row_count == 45
    assert set(summary["by_system"]) == {system.value for system in Q5AgentSystem}
    for metrics in summary["by_system"].values():
        assert metrics["task_success"] == 1.0
        assert metrics["terminal_action_correct"] == 1.0
        assert metrics["required_observation_recall"] == 1.0
        assert metrics["invalid_transition_rate"] == 0.0
        assert metrics["unauthorized_action_blocked"] == 1.0
        assert metrics["F11"] == metrics["F13"] == metrics["F17"] == 0
        assert metrics["restricted_text_exposure_count"] == 0
        assert metrics["unsafe_tool_call_count"] == 0
        assert metrics["pass_1"] == metrics["pass_3"] == 1.0
        assert metrics["trajectory_consistency"] == 1.0
    assert summary["comparisons"]["paired_bootstrap_ci"]["resamples"] == 10_000
    control = summary["analytic_controls"]["q5_escalate_everything_control"]
    assert control["anti_gaming_failure"] is True
    assert control["anti_gaming_ok"] is False
    assert gates["system_headline_eligibility"][
        "q5_escalate_everything_control"
    ] is False
    assert _jsonl(graded.analytic_controls_path)
    assert "Anti-gaming failure detected: `True`" in graded.report_path.read_text(
        encoding="utf-8"
    )
    assert gates["q5_headline_eligible"] is False
    assert "mock_dev_or_non_test_run" in gates["headline_blockers"]
    assert len(graded_manifest["dataset_hashes"]["gold"]) == 64
    assert "gold" not in manifest["dataset_hashes"]
    assert graded.report_path.read_text(encoding="utf-8").startswith(
        "# Q5 Outcome Evaluation"
    )


def test_q5_restricted_completion_is_f17_and_hard_invalid(tmp_path: Path) -> None:
    task = load_q5_tasks(TASKS_PATH)[0]
    environment = load_q5_environment(ENVIRONMENT_PATH)
    runtime_case = _runtime_cases([task])[task.case_id]
    blocked = make_retrieved_chunk(
        "blocked-q5-p4-canary",
        RESTRICTED_CANARY,
        doc_id="doc-restricted-canary",
        rerank_score=0.99,
    )
    pass_result = runtime_case.pass_result.model_copy(
        update={
            "acl_decision": ACLGateDecision(
                surviving_chunks=runtime_case.pass_result.acl_decision.surviving_chunks,
                blocked_chunks=[blocked],
            )
        }
    )
    runtime_case = runtime_case.model_copy(update={"pass_result": pass_result})
    raw = run_q5_tasks(
        [task],
        environment,
        list(Q5AgentSystem),
        runtime_cases={task.case_id: runtime_case},
        settings=Q5RunSettings(
            output_root=tmp_path,
            run_id="q5-p4-restricted-negative",
            k=1,
            seed=7,
            bootstrap_resamples=10_000,
            mode="mock",
        ),
        model_factory=lambda task, system, run_index: RestrictedEchoModel(),
    )
    raw_row = next(
        row
        for row in _jsonl(raw.results_path)
        if row["system"] == Q5AgentSystem.llm.value
    )
    assert raw_row["restricted_text_exposure_count"] == 1

    gold_path = tmp_path / "single-gold.jsonl"
    gold_path.write_text(
        GOLD_PATH.read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    graded = grade_q5_run(raw.run_dir, gold_path)
    graded_row = next(
        row
        for row in _jsonl(graded.graded_rows_path)
        if row["system"] == Q5AgentSystem.llm.value
    )
    gates = _json(graded.gates_path)
    assert graded_row["F17"] is True
    assert gates["run_valid"] is False
    assert gates["q5_headline_eligible"] is False


def test_q5_grader_marks_missing_observation_and_outcome_mismatch(
    tmp_path: Path,
) -> None:
    task = load_q5_tasks(TASKS_PATH)[0]
    environment = load_q5_environment(ENVIRONMENT_PATH)
    runtime_case = _runtime_cases([task])[task.case_id]
    raw = run_q5_tasks(
        [task],
        environment,
        list(Q5AgentSystem),
        runtime_cases={task.case_id: runtime_case},
        settings=Q5RunSettings(
            output_root=tmp_path,
            run_id="q5-p4-outcome-negative",
            k=1,
            seed=11,
            bootstrap_resamples=10_000,
            mode="mock",
        ),
        model_factory=lambda task, system, run_index: Q5DeterministicMockPolicyModel(),
    )
    grader_gold = json.loads(
        GOLD_PATH.read_text(encoding="utf-8").splitlines()[0]
    )
    grader_gold["required_observations"] = ["lookup_policy_exception"]
    grader_gold["final_state_assertions"] = [
        {
            "path": "records",
            "operator": "contains",
            "value": {"action": "send_alert"},
        }
    ]
    gold_path = tmp_path / "mismatch-gold.jsonl"
    gold_path.write_text(json.dumps(grader_gold) + "\n", encoding="utf-8")

    graded = grade_q5_run(raw.run_dir, gold_path)
    row = _jsonl(graded.graded_rows_path)[0]
    assert row["terminal_action_correct"] is True
    assert row["task_success"] is False
    assert row["F15"] is True
    assert row["F16"] is True


def test_q5_real_mode_rejects_spoofed_model_before_execution(tmp_path: Path) -> None:
    task = load_q5_tasks(TASKS_PATH)[0]
    environment = load_q5_environment(ENVIRONMENT_PATH)
    spoof = SpoofRealModel()
    run_dir = tmp_path / "q5-real-spoof"

    with pytest.raises(ValueError, match="before execution"):
        run_q5_tasks(
            [task],
            environment,
            [Q5AgentSystem.llm],
            runtime_cases=_runtime_cases([task]),
            settings=Q5RunSettings(
                output_root=tmp_path,
                run_id=run_dir.name,
                k=1,
                mode="real",
            ),
            model_factory=lambda task, system, run_index: spoof,
        )

    assert spoof.generate_calls == 0
    assert spoof.metadata_calls == 0
    assert not run_dir.exists()


@pytest.mark.parametrize("mutation", ["delete", "duplicate"])
def test_q5_grader_hard_fails_tampered_trial_ledger_after_rehash(
    tmp_path: Path,
    mutation: str,
) -> None:
    raw, gold_path = _single_case_raw_run(
        tmp_path,
        run_id=f"q5-ledger-{mutation}",
    )
    rows = _jsonl(raw.results_path)
    if mutation == "delete":
        rows = rows[:-1]
    else:
        rows.append(dict(rows[0]))
    raw.results_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest = _json(raw.manifest_path)
    manifest["artifact_row_counts"]["results.jsonl"] = len(rows)
    raw.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _refresh_raw_hash(raw.run_dir, "results.jsonl")
    _refresh_raw_hash(raw.run_dir, "manifest.json")

    with pytest.raises(ValueError, match="duplicate|missing"):
        grade_q5_run(raw.run_dir, gold_path)


def test_q5_grader_rejects_extra_raw_artifact(tmp_path: Path) -> None:
    raw, gold_path = _single_case_raw_run(tmp_path, run_id="q5-extra-artifact")
    (raw.run_dir / "unexpected.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact closure mismatch"):
        grade_q5_run(raw.run_dir, gold_path)


def test_q5_dual_model_summary_verifies_hashes_roles_and_distinct_models(
    tmp_path: Path,
) -> None:
    primary, _ = _single_case_graded_run(
        tmp_path,
        run_id="q5-dual-primary",
        role="primary",
        model=Q5DeterministicMockPolicyModel(),
    )
    confirmatory, _ = _single_case_graded_run(
        tmp_path,
        run_id="q5-dual-confirmatory",
        role="confirmatory",
        model=AlternateMockPolicyModel(),
    )
    combined = summarize_q5_model_roles(
        primary.run_dir,
        confirmatory.run_dir,
        tmp_path / "combined",
    )
    verified = verify_q5_dual_summary(combined.output_dir)

    assert len(verified["ledger"]) == 2
    assert verified["gates"]["verified_run_count_by_model_role"] == {
        "confirmatory": 1,
        "primary": 1,
    }
    assert verified["gates"]["q5_headline_eligible"] is False
    combined_payload = _json(combined.summary_path)
    combined_payload["by_model_role"]["primary"] = combined_payload[
        "by_model_role"
    ]["confirmatory"]
    combined.summary_path.write_text(
        json.dumps(combined_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    combined_hashes = _json(combined.hashes_path)
    combined_hashes["artifacts"]["combined_summary.json"] = hashlib.sha256(
        combined.summary_path.read_bytes()
    ).hexdigest()
    combined.hashes_path.write_text(
        json.dumps(combined_hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="model-role provenance"):
        verify_q5_dual_summary(combined.output_dir)


def test_q5_dual_model_summary_rejects_wrong_role_same_model_and_tamper(
    tmp_path: Path,
) -> None:
    primary, _ = _single_case_graded_run(
        tmp_path,
        run_id="q5-negative-primary",
        role="primary",
        model=Q5DeterministicMockPolicyModel(),
    )
    wrong_role, _ = _single_case_graded_run(
        tmp_path,
        run_id="q5-negative-wrong-role",
        role="primary",
        model=AlternateMockPolicyModel(),
    )
    with pytest.raises(ValueError, match="confirmatory model role"):
        summarize_q5_model_roles(
            primary.run_dir,
            wrong_role.run_dir,
            tmp_path / "wrong-role-combined",
        )

    same_model, _ = _single_case_graded_run(
        tmp_path,
        run_id="q5-negative-same-model",
        role="confirmatory",
        model=Q5DeterministicMockPolicyModel(),
    )
    with pytest.raises(ValueError, match="distinct models"):
        summarize_q5_model_roles(
            primary.run_dir,
            same_model.run_dir,
            tmp_path / "same-model-combined",
        )

    same_provider, _ = _single_case_graded_run(
        tmp_path,
        run_id="q5-negative-same-provider",
        role="confirmatory",
        model=SameProviderAlternateMockPolicyModel(),
    )
    with pytest.raises(ValueError, match="distinct provider families"):
        summarize_q5_model_roles(
            primary.run_dir,
            same_provider.run_dir,
            tmp_path / "same-provider-combined",
        )

    summary_path = wrong_role.run_dir / "summary.json"
    summary_path.write_text(summary_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_q5_graded_run(wrong_role.run_dir)


def test_q5_missing_control_artifact_is_not_verifiable(tmp_path: Path) -> None:
    graded, _ = _single_case_graded_run(
        tmp_path,
        run_id="q5-missing-control",
        role="primary",
        model=Q5DeterministicMockPolicyModel(),
    )
    graded.analytic_controls_path.unlink()

    with pytest.raises(ValueError, match="artifact closure mismatch"):
        verify_q5_graded_run(graded.run_dir)


def test_q5_execution_and_grading_clis_run_synthetic_fixture(tmp_path: Path) -> None:
    task = load_q5_tasks(TASKS_PATH)[0]
    runtime_case = _runtime_cases([task])[task.case_id]
    tasks_path = tmp_path / "tasks.jsonl"
    environment_path = tmp_path / "environment.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    gold_path = tmp_path / "gold.jsonl"
    tasks_path.write_text(
        TASKS_PATH.read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    environment_path.write_text(
        ENVIRONMENT_PATH.read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    runtime_path.write_text(
        json.dumps(runtime_case.model_dump(mode="json"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    gold_path.write_text(
        GOLD_PATH.read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    run_payload = run_q5_cli(
        [
            "--tasks",
            str(tasks_path),
            "--environment",
            str(environment_path),
            "--runtime-cases",
            str(runtime_path),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "q5-cli-synthetic",
            "--k",
            "1",
        ]
    )
    grade_payload = grade_q5_cli(
        [
            "grade",
            "--run-dir",
            str(run_payload["run_dir"]),
            "--gold",
            str(gold_path),
        ]
    )

    assert run_payload["trial_count"] == 3
    assert grade_payload["row_count"] == 3
    assert Path(str(grade_payload["summary"])).is_file()


def _single_case_raw_run(
    tmp_path: Path,
    *,
    run_id: str,
    role: str = "primary",
    model: Q5DeterministicMockPolicyModel | None = None,
):
    task = load_q5_tasks(TASKS_PATH)[0]
    environment = load_q5_environment(ENVIRONMENT_PATH)
    selected_model = model or Q5DeterministicMockPolicyModel()
    raw = run_q5_tasks(
        [task],
        environment,
        list(Q5AgentSystem),
        runtime_cases=_runtime_cases([task]),
        settings=Q5RunSettings(
            output_root=tmp_path,
            run_id=run_id,
            k=1,
            seed=41,
            bootstrap_resamples=10_000,
            mode="mock",
            model_role=role,
        ),
        model_factory=lambda task, system, run_index: selected_model,
    )
    gold_path = tmp_path / f"{run_id}-gold.jsonl"
    gold_path.write_text(
        GOLD_PATH.read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    return raw, gold_path


def _single_case_graded_run(
    tmp_path: Path,
    *,
    run_id: str,
    role: str,
    model: Q5DeterministicMockPolicyModel,
):
    raw, gold_path = _single_case_raw_run(
        tmp_path,
        run_id=run_id,
        role=role,
        model=model,
    )
    return grade_q5_run(raw.run_dir, gold_path), gold_path


def _refresh_raw_hash(run_dir: Path, filename: str) -> None:
    hashes_path = run_dir / "hashes.json"
    payload = _json(hashes_path)
    payload["artifacts"][filename] = hashlib.sha256(
        (run_dir / filename).read_bytes()
    ).hexdigest()
    hashes_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _runtime_cases(tasks: list[Q5TaskInput]) -> dict[str, Q5RuntimeCaseInput]:
    cases: dict[str, Q5RuntimeCaseInput] = {}
    condition_by_case = {
        "q5-p4-committed": [OpsCondition.stale_procedure],
        "q5-p4-pending": [OpsCondition.config_violation],
        "q5-p4-escalated": [OpsCondition.config_violation],
        "q5-p4-noop": [],
        "q5-p4-unauthorized": [OpsCondition.permission_blocked],
    }
    for task in tasks:
        doc_id = f"doc-{task.case_id}"
        chunk_id = f"chunk-{task.case_id}"
        evidence = make_retrieved_chunk(
            chunk_id,
            f"Authorized runtime evidence for {' '.join(task.resource_refs)}.",
            doc_id=doc_id,
            rerank_score=0.95,
        )
        evidence = evidence.model_copy(
            update={
                "chunk": evidence.chunk.model_copy(
                    update={
                        "source_origin": SourceOrigin.public_repo,
                        "corpus_source": CorpusSource.public_external,
                    }
                )
            }
        )
        pass_result = RetrievalPassResult(
            query=task.query,
            retrieved_chunks=[evidence],
            reranked_chunks=[evidence],
            state_decision=StateGateDecision(surviving_chunks=[evidence]),
            acl_decision=ACLGateDecision(surviving_chunks=[evidence]),
            conflict_decision=ConflictDecision(),
            evidence_decision=EvidenceGateDecision(
                evidence_sufficient=True,
                reason="sufficient synthetic fixture evidence",
                top_score=0.95,
                support_count=1,
            ),
        )
        conditions = condition_by_case[task.case_id]
        report = ConditionReport(
            conditions=conditions,
            authorized_actor=task.case_id != "q5-p4-unauthorized",
            evidence_decision="sufficient",
            stale_doc_ids=(
                [doc_id] if OpsCondition.stale_procedure in conditions else []
            ),
            violating_doc_ids=(
                [doc_id] if OpsCondition.config_violation in conditions else []
            ),
            permission_blocked_count=(
                1 if OpsCondition.permission_blocked in conditions else 0
            ),
        )
        cases[task.case_id] = Q5RuntimeCaseInput(
            case_id=task.case_id,
            pass_result=pass_result,
            report=report,
        )
    return cases


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _key(case_id: str, system: str, run_index: int) -> str:
    return f"{case_id}|{system}|{run_index}"


def _indexed_environments(path: Path) -> dict[str, dict]:
    return {
        _key(row["case_id"], row["system"], row["run_index"]): row["environment"]
        for row in _json(path)
    }


def _assert_no_gold_keys(payload) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key not in Q5_GOLD_ONLY_FIELDS
            assert not key.startswith("gold_")
            _assert_no_gold_keys(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_gold_keys(value)
