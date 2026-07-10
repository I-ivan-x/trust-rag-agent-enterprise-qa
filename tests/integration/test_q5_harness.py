from __future__ import annotations

import inspect
import json
from pathlib import Path

from app.core.enums import CorpusSource, SourceOrigin
from app.eval.q5_dataset import load_q5_environment, load_q5_tasks
from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_runner import (
    Q5RunSettings,
    Q5RuntimeCaseInput,
    grade_q5_run,
    run_q5_tasks,
)
from app.govern.conditions import ConditionReport, OpsCondition
from app.govern.q5_loop import Q5AgentSystem
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.schemas.q5_task import Q5_GOLD_ONLY_FIELDS, Q5TaskInput
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk

FIXTURE_ROOT = Path("tests/fixtures/q5_p4")
TASKS_PATH = FIXTURE_ROOT / "tasks.jsonl"
ENVIRONMENT_PATH = FIXTURE_ROOT / "environment.jsonl"
GOLD_PATH = FIXTURE_ROOT / "gold.jsonl"
RESTRICTED_CANARY = "Q5_P4_RESTRICTED_CANARY_MUST_INVALIDATE_RUN"


class RestrictedEchoModel:
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
        provider="deterministic_mock",
        model_name="q5-runtime-policy-v1",
        mock_used=True,
        real_run=False,
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
        [Q5AgentSystem.llm],
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
    raw_row = _jsonl(raw.results_path)[0]
    assert raw_row["restricted_text_exposure_count"] == 1

    gold_path = tmp_path / "single-gold.jsonl"
    gold_path.write_text(
        GOLD_PATH.read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    graded = grade_q5_run(raw.run_dir, gold_path)
    graded_row = _jsonl(graded.graded_rows_path)[0]
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
        [Q5AgentSystem.rule],
        runtime_cases={task.case_id: runtime_case},
        settings=Q5RunSettings(
            output_root=tmp_path,
            run_id="q5-p4-outcome-negative",
            k=1,
            seed=11,
            bootstrap_resamples=10_000,
            mode="mock",
        ),
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
