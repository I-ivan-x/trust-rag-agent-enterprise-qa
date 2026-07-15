from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_provenance import verify_q5_graded_run
from app.eval.q5_runner import _validate_q5_v4_trial_provenance, grade_q5_run
from app.govern.q5_loop import Q5AgentSystem
from tests.integration.test_q5_harness import (
    InvalidAliasMockPolicyModel,
    _jsonl,
    _pending_case_raw_run,
    _refresh_raw_hash,
    _refresh_trajectory_result_hash,
    _write_test_jsonl,
)

_LLM = Q5AgentSystem.llm.value


def test_q5_v4_lineage_validator_has_no_gold_or_semantic_label_inputs() -> None:
    source = inspect.getsource(_validate_q5_v4_trial_provenance).lower()
    for forbidden in ("gold", "case_id", "stratum", "pair", "expected_action"):
        assert forbidden not in source


@pytest.mark.parametrize(
    "mutation",
    [
        "result_disposition",
        "result_action",
        "result_source",
        "result_evidence",
        "result_request",
        "policy_terminal_proposal",
        "terminal_disposition",
        "terminal_action",
        "terminal_basis",
        "terminal_source",
        "trajectory_disposition",
        "trajectory_action",
        "trajectory_source",
        "transition_action",
        "foreign_request",
        "stale_request",
        "timeout_request",
        "unauthorized_evidence",
        "uncited_evidence",
        "cross_trial_evidence",
        "synchronized_multi_ledger_action",
        "synchronized_multi_ledger_evidence",
    ],
)
@pytest.mark.parametrize("entrypoint", ["grade", "verify"])
def test_q5_v4_rehashed_policy_lineage_mutation_matrix_fails_closed(
    tmp_path: Path,
    mutation: str,
    entrypoint: str,
) -> None:
    raw, gold_path = _pending_case_raw_run(
        tmp_path,
        run_id=f"q5-v4-lineage-{entrypoint}-{mutation}",
        model=Q5DeterministicMockPolicyModel(),
    )
    if entrypoint == "verify":
        grade_q5_run(raw.run_dir, gold_path)

    _mutate_and_rehash(raw.run_dir, mutation)

    with pytest.raises(ValueError):
        if entrypoint == "grade":
            grade_q5_run(raw.run_dir, gold_path)
        else:
            verify_q5_graded_run(raw.run_dir, gold_path)


def test_q5_v4_valid_rule_model_fallback_timeout_lineage_passes(
    tmp_path: Path,
) -> None:
    normal, normal_gold = _pending_case_raw_run(
        tmp_path,
        run_id="q5-v4-lineage-valid-normal",
        model=Q5DeterministicMockPolicyModel(),
    )
    fallback, fallback_gold = _pending_case_raw_run(
        tmp_path,
        run_id="q5-v4-lineage-valid-fallback",
        model=InvalidAliasMockPolicyModel(),
    )
    timeout, timeout_gold = _pending_case_raw_run(
        tmp_path,
        run_id="q5-v4-lineage-valid-timeout",
        model=Q5DeterministicMockPolicyModel(),
        timeout=True,
    )

    for raw, gold in (
        (normal, normal_gold),
        (fallback, fallback_gold),
        (timeout, timeout_gold),
    ):
        graded = grade_q5_run(raw.run_dir, gold)
        assert verify_q5_graded_run(graded.run_dir, gold).protocol_version == "v4"

    normal_sources = {
        row["disposition_source"] for row in _jsonl(normal.results_path)
    }
    assert normal_sources == {"rule", "model"}
    assert {
        row["disposition_source"] for row in _jsonl(fallback.results_path)
    } == {"rule", "fallback"}
    assert all(
        row["decision_basis_observation_request_id"] is None
        for row in _jsonl(timeout.results_path)
    )


def _mutate_and_rehash(run_dir: Path, mutation: str) -> None:
    paths = {
        name: run_dir / name
        for name in (
            "results.jsonl",
            "policy_events.jsonl",
            "terminal_events.jsonl",
            "trajectory.jsonl",
            "tool_events.jsonl",
        )
    }
    rows = {name: _jsonl(path) for name, path in paths.items()}
    result = next(row for row in rows["results.jsonl"] if row["system"] == _LLM)
    terminal = next(
        row for row in rows["terminal_events.jsonl"] if row["system"] == _LLM
    )
    terminal_proposal = terminal["terminal_proposal"]
    terminal_policy = next(
        row
        for row in rows["policy_events.jsonl"]
        if row["system"] == _LLM
        and row.get("accepted_proposal", {}).get("kind") == "terminal"
    )
    terminal_trajectory = next(
        row
        for row in rows["trajectory.jsonl"]
        if row["system"] == _LLM and row["event_type"] == "terminal"
    )

    if mutation.startswith("result_"):
        field, value = {
            "result_disposition": ("policy_disposition", "no_action"),
            "result_action": ("final_action", "no_op"),
            "result_source": ("disposition_source", "rule"),
            "result_evidence": (
                "decision_basis_evidence_chunk_id",
                "chunk-foreign-evidence",
            ),
            "result_request": (
                "decision_basis_observation_request_id",
                "q5-tool-stale",
            ),
        }[mutation]
        result[field] = value
    elif mutation == "policy_terminal_proposal":
        terminal_policy["accepted_proposal"]["reason_code"] = "forged_terminal"
    elif mutation == "terminal_disposition":
        terminal_proposal["decision_basis"]["policy_disposition"] = "no_action"
    elif mutation == "terminal_action":
        terminal_proposal["action"] = "no_op"
    elif mutation == "terminal_basis":
        terminal_proposal["decision_basis"]["evidence_chunk_id"] = (
            "chunk-foreign-evidence"
        )
    elif mutation == "terminal_source":
        terminal_proposal["disposition_source"] = "rule"
    elif mutation.startswith("trajectory_"):
        field, value = {
            "trajectory_disposition": ("policy_disposition", "no_action"),
            "trajectory_action": ("action", "no_op"),
            "trajectory_source": ("disposition_source", "rule"),
        }[mutation]
        terminal_trajectory[field] = value
    elif mutation == "transition_action":
        terminal["transition"]["action"] = "no_op"
    elif mutation in {"foreign_request", "stale_request"}:
        terminal_proposal["decision_basis"]["observation_request_id"] = (
            "q5-tool-foreign" if mutation == "foreign_request" else "q5-tool-stale"
        )
    elif mutation == "timeout_request":
        request_id = terminal_proposal["decision_basis"]["observation_request_id"]
        tool = next(
            row
            for row in rows["tool_events.jsonl"]
            if row["system"] == _LLM and row["request_id"] == request_id
        )
        tool["status"] = "timeout"
        tool["observation"] = None
        observation = next(
            row
            for row in rows["trajectory.jsonl"]
            if row["system"] == _LLM and row["event_type"] == "observation"
        )
        observation["tool_status"] = "timeout"
    elif mutation in {"unauthorized_evidence", "cross_trial_evidence"}:
        evidence_id = (
            "chunk-unauthorized"
            if mutation == "unauthorized_evidence"
            else "chunk-other-trial"
        )
        terminal_proposal["decision_basis"]["evidence_chunk_id"] = evidence_id
        terminal_proposal["evidence_chunk_ids"] = [evidence_id]
    elif mutation == "uncited_evidence":
        terminal_proposal["evidence_chunk_ids"] = []
    elif mutation == "synchronized_multi_ledger_action":
        result["final_action"] = "no_op"
        result["policy_disposition"] = "no_action"
        terminal["final_action"] = "no_op"
        terminal["transition"]["action"] = "no_op"
        terminal_proposal["action"] = "no_op"
        terminal_proposal["decision_basis"]["policy_disposition"] = "no_action"
        terminal_trajectory["action"] = "no_op"
        terminal_trajectory["policy_disposition"] = "no_action"
    elif mutation == "synchronized_multi_ledger_evidence":
        evidence_id = "chunk-other-trial"
        result["authorized_evidence_ids"] = [evidence_id]
        result["decision_basis_evidence_chunk_id"] = evidence_id
        terminal_proposal["decision_basis"]["evidence_chunk_id"] = evidence_id
        terminal_proposal["evidence_chunk_ids"] = [evidence_id]
        terminal_policy["accepted_proposal"]["decision_basis"][
            "evidence_chunk_id"
        ] = evidence_id
        terminal_policy["accepted_proposal"]["evidence_chunk_ids"] = [evidence_id]
    else:  # pragma: no cover - matrix guard
        raise AssertionError(mutation)

    for name, path in paths.items():
        _write_test_jsonl(path, rows[name])
        _refresh_raw_hash(run_dir, name)
    if mutation.startswith("trajectory_") or mutation in {
        "timeout_request",
        "synchronized_multi_ledger_action",
    }:
        _refresh_trajectory_result_hash(run_dir, _LLM)
