from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.eval.q5_dataset import (
    Q5EnvironmentStore,
    load_q5_environment,
    load_q5_tasks,
)
from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_provenance import verify_q5_graded_run
from app.eval.q5_runner import (
    Q5RunSettings,
    grade_q5_run,
    run_q5_tasks,
)
from app.govern.conditions import ConditionReport, OpsCondition
from app.govern.q5_loop import Q5AgentSystem
from tests.integration.test_q5_harness import (
    ENVIRONMENT_PATH,
    GOLD_PATH,
    TASKS_PATH,
    _json,
    _jsonl,
    _pending_case_raw_run,
    _refresh_raw_hash,
    _refresh_trajectory_result_hash,
    _runtime_cases,
    _write_test_jsonl,
)

_RULE = Q5AgentSystem.rule.value


class AlwaysObserveMockPolicyModel(Q5DeterministicMockPolicyModel):
    def generate(self, prompt: str) -> str:
        del prompt
        return json.dumps(
            {
                "kind": "observe",
                "tool": "lookup_policy_exception",
                "args": {
                    "resource_ref": "resource:payments",
                    "policy_ref": "policy:change-control",
                },
                "decision_basis": None,
                "evidence_chunk_ids": ["chunk-q5-p4-pending"],
                "reason_code": "retry_timeout_within_policy_budget",
                "reason_summary": "The bounded policy step replans the observation.",
            }
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "ordinary_rule_human_review_spoof",
        "route_reason_only",
        "candidate_actions_only",
        "synchronized_without_block_fact",
        "transplanted_policy_block",
        "evidence_sufficient_contradiction",
    ],
)
@pytest.mark.parametrize("entrypoint", ["grade", "verify"])
def test_q5_hr3_rehashed_policy_block_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
    entrypoint: str,
) -> None:
    block_source = mutation in {
        "candidate_actions_only",
        "evidence_sufficient_contradiction",
    }
    if block_source:
        raw, gold = _fixture_policy_block_run(
            tmp_path,
            run_id=f"q5-hr3-{entrypoint}-{mutation}",
            block_kind="insufficient",
        )
    else:
        raw, gold = _ordinary_rule_human_review_run(
            tmp_path,
            run_id=f"q5-hr3-{entrypoint}-{mutation}",
        )
    if entrypoint == "verify":
        grade_q5_run(raw.run_dir, gold)

    donor_dir: Path | None = None
    if mutation == "transplanted_policy_block":
        donor, _ = _fixture_policy_block_run(
            tmp_path,
            run_id=f"q5-hr3-donor-{entrypoint}",
            block_kind="permission",
        )
        donor_dir = donor.run_dir
    _mutate_policy_block(raw.run_dir, mutation, donor_dir=donor_dir)

    with pytest.raises(ValueError):
        if entrypoint == "grade":
            grade_q5_run(raw.run_dir, gold)
        else:
            verify_q5_graded_run(raw.run_dir, gold)


@pytest.mark.parametrize("block_kind", ["insufficient", "permission"])
def test_q5_hr3_legitimate_runtime_policy_blocks_verify(
    tmp_path: Path,
    block_kind: str,
) -> None:
    raw, gold = _fixture_policy_block_run(
        tmp_path,
        run_id=f"q5-hr3-valid-{block_kind}",
        block_kind=block_kind,
    )
    graded = grade_q5_run(raw.run_dir, gold)

    assert verify_q5_graded_run(graded.run_dir, gold).protocol_version == "v4"
    results = _jsonl(raw.results_path)
    terminals = _jsonl(raw.run_dir / "terminal_events.jsonl")
    assert {tuple(row["route_reasons"]) for row in results} == {
        ("terminal_policy_block",)
    }
    assert all(row["fallback_reason"] is None for row in results)
    assert all(row["disposition_source"] == "fallback" for row in results)
    assert all(
        row["route"]["candidate_terminal_actions"] == ["escalate_to_human"]
        for row in terminals
    )


def test_q5_hr3_persistent_timeout_has_one_bounded_terminal_cause(
    tmp_path: Path,
) -> None:
    raw, gold = _pending_case_raw_run(
        tmp_path,
        run_id="q5-hr3-persistent-timeout",
        model=AlwaysObserveMockPolicyModel(),
        timeout=True,
    )
    graded = grade_q5_run(raw.run_dir, gold)

    assert verify_q5_graded_run(graded.run_dir, gold).protocol_version == "v4"
    results = {
        row["system"]: row for row in _jsonl(raw.results_path)
    }
    for system in (Q5AgentSystem.llm.value, Q5AgentSystem.hybrid.value):
        assert results[system]["fallback_reason"] == "step_budget_exhausted"
        events = [
            row
            for row in _jsonl(raw.run_dir / "tool_events.jsonl")
            if row["system"] == system
        ]
        assert [row["request_id"] for row in events] == [
            "q5-tool-0001",
            "q5-tool-0002",
        ]
        assert [row["status"] for row in events] == ["timeout", "timeout"]
        assert results[system]["duplicate_successful_observation_count"] == 0


def test_q5_hr3_runtime_attestation_cannot_be_downgraded(
    tmp_path: Path,
) -> None:
    raw, gold = _ordinary_rule_human_review_run(
        tmp_path,
        run_id="q5-hr3-attestation-downgrade",
    )
    manifest = _json(raw.manifest_path)
    del manifest["runtime_attestation"]
    raw.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    hashes = _json(raw.hashes_path)
    hashes["artifacts"]["manifest.json"] = hashlib.sha256(
        raw.manifest_path.read_bytes()
    ).hexdigest()
    raw.hashes_path.write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cannot be downgraded"):
        grade_q5_run(raw.run_dir, gold)


def _ordinary_rule_human_review_run(tmp_path: Path, *, run_id: str):
    task = next(
        item for item in load_q5_tasks(TASKS_PATH) if item.case_id == "q5-p4-pending"
    )
    source = load_q5_environment(ENVIRONMENT_PATH)[task.environment_ref]
    source = source.model_copy(
        update={
            "policy_exceptions": {
                "resource:payments|policy:change-control": {
                    "status": "active",
                    "scope": "staging",
                }
            }
        }
    )
    raw = run_q5_tasks(
        [task],
        Q5EnvironmentStore.from_states([source]),
        list(Q5AgentSystem),
        runtime_cases=_runtime_cases([task]),
        settings=Q5RunSettings(
            output_root=tmp_path,
            run_id=run_id,
            k=1,
            seed=20260716,
            bootstrap_resamples=10_000,
            mode="mock",
        ),
        model_factory=lambda task, system, run_index: Q5DeterministicMockPolicyModel(),
    )
    gold = tmp_path / f"{run_id}-gold.jsonl"
    gold.write_text(
        next(
            line
            for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["case_id"] == task.case_id
        )
        + "\n",
        encoding="utf-8",
    )
    rule = next(row for row in _jsonl(raw.results_path) if row["system"] == _RULE)
    assert rule["final_action"] == "escalate_to_human"
    assert rule["disposition_source"] == "rule"
    assert rule["evidence_decision"] == "sufficient"
    return raw, gold


def _fixture_policy_block_run(
    tmp_path: Path,
    *,
    run_id: str,
    block_kind: str,
):
    case_id = (
        "q5-p4-unauthorized"
        if block_kind == "permission"
        else "q5-p4-pending"
    )
    task = next(item for item in load_q5_tasks(TASKS_PATH) if item.case_id == case_id)
    environment = load_q5_environment(ENVIRONMENT_PATH)
    source = environment[task.environment_ref]
    runtime_case = _runtime_cases([task])[case_id]
    if block_kind == "insufficient":
        runtime_case = runtime_case.model_copy(
            update={
                "report": ConditionReport(
                    conditions=[OpsCondition.insufficient_evidence],
                    authorized_actor=True,
                    evidence_decision="insufficient",
                    violating_doc_ids=[f"doc-{case_id}"],
                )
            }
        )
    raw = run_q5_tasks(
        [task],
        Q5EnvironmentStore.from_states([source]),
        list(Q5AgentSystem),
        runtime_cases={case_id: runtime_case},
        settings=Q5RunSettings(
            output_root=tmp_path,
            run_id=run_id,
            k=1,
            seed=20260716,
            bootstrap_resamples=10_000,
            mode="mock",
        ),
        model_factory=lambda task, system, run_index: Q5DeterministicMockPolicyModel(),
    )
    gold = tmp_path / f"{run_id}-gold.jsonl"
    gold.write_text(
        next(
            line
            for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["case_id"] == case_id
        )
        + "\n",
        encoding="utf-8",
    )
    return raw, gold


def _mutate_policy_block(
    run_dir: Path,
    mutation: str,
    *,
    donor_dir: Path | None,
) -> None:
    names = (
        "results.jsonl",
        "policy_events.jsonl",
        "terminal_events.jsonl",
        "trajectory.jsonl",
    )
    rows = {name: _jsonl(run_dir / name) for name in names}
    result, terminal, policy, trajectory = _rule_ledgers(rows)

    if mutation == "ordinary_rule_human_review_spoof":
        _forge_policy_block(result, terminal, policy, trajectory, forge_route=True)
    elif mutation == "route_reason_only":
        result["route_reasons"] = ["terminal_policy_block"]
        terminal["route"]["route_reasons"] = ["terminal_policy_block"]
    elif mutation == "candidate_actions_only":
        terminal["route"]["candidate_terminal_actions"] = [
            "escalate_to_human",
            "no_op",
        ]
    elif mutation == "synchronized_without_block_fact":
        _forge_policy_block(result, terminal, policy, trajectory, forge_route=False)
    elif mutation == "transplanted_policy_block":
        assert donor_dir is not None
        donor_rows = {
            name: _jsonl(donor_dir / name)
            for name in names
        }
        _, donor_terminal, _, _ = _rule_ledgers(donor_rows)
        _forge_policy_block(result, terminal, policy, trajectory, forge_route=True)
        terminal["q4_validation_input"]["report"] = copy.deepcopy(
            donor_terminal["q4_validation_input"]["report"]
        )
    elif mutation == "evidence_sufficient_contradiction":
        terminal["q4_validation_input"]["report"]["conditions"] = []
        terminal["q4_validation_input"]["report"]["evidence_decision"] = "sufficient"
        result["evidence_decision"] = "sufficient"
    else:  # pragma: no cover
        raise AssertionError(mutation)

    for name, payload in rows.items():
        _write_test_jsonl(run_dir / name, payload)
        _refresh_raw_hash(run_dir, name)
    _refresh_trajectory_result_hash(run_dir, _RULE)


def _rule_ledgers(rows: dict[str, list[dict]]):
    result = next(row for row in rows["results.jsonl"] if row["system"] == _RULE)
    terminal = next(
        row for row in rows["terminal_events.jsonl"] if row["system"] == _RULE
    )
    trajectory = next(
        row
        for row in rows["trajectory.jsonl"]
        if row["system"] == _RULE and row["event_type"] == "terminal"
    )
    policy = next(
        row
        for row in rows["policy_events.jsonl"]
        if row["system"] == _RULE
        and isinstance(row.get("accepted_proposal"), dict)
        and row["accepted_proposal"].get("kind") == "terminal"
    )
    return result, terminal, policy, trajectory


def _forge_policy_block(
    result: dict,
    terminal: dict,
    policy: dict,
    trajectory: dict,
    *,
    forge_route: bool,
) -> None:
    proposal = terminal["terminal_proposal"]
    assert proposal["action"] == "escalate_to_human"
    proposal["decision_basis"] = None
    proposal["disposition_source"] = "fallback"
    proposal["reason_code"] = "policy_block"
    policy["accepted_proposal"] = copy.deepcopy(proposal)
    result["policy_disposition"] = None
    result["disposition_source"] = "fallback"
    result["decision_basis_evidence_chunk_id"] = None
    result["decision_basis_observation_request_id"] = None
    result["fallback_reason"] = None
    trajectory["policy_disposition"] = None
    trajectory["disposition_source"] = "fallback"
    trajectory["reason_code"] = "policy_block"
    if forge_route:
        result["route"] = "rule"
        result["route_reasons"] = ["terminal_policy_block"]
        terminal["route"]["route"] = "rule"
        terminal["route"]["route_reasons"] = ["terminal_policy_block"]
        terminal["route"]["candidate_terminal_actions"] = ["escalate_to_human"]
