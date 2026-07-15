from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

import app.eval.q5_fallback as q5_fallback_module
import app.govern.q5_loop as q5_loop_module
from app.eval.q5_fallback import derive_q5_v4_fallback_witness
from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_provenance import verify_q5_graded_run
from app.eval.q5_runner import grade_q5_run
from app.govern.conditions import GovernanceAction
from app.govern.q5_fallback import Q5FallbackCause
from app.govern.q5_loop import Q5AgentSystem
from app.govern.validator import GovValidationResult
from tests.integration.test_q5_harness import (
    _json,
    _jsonl,
    _pending_case_raw_run,
    _refresh_raw_hash,
    _refresh_trajectory_result_hash,
    _write_test_jsonl,
)

_LLM = Q5AgentSystem.llm.value


class HumanReviewMockPolicyModel(Q5DeterministicMockPolicyModel):
    def generate(self, prompt: str) -> str:
        payload = json.loads(super().generate(prompt))
        if payload["kind"] == "terminal":
            payload["decision_basis"]["policy_disposition"] = "human_review"
        return json.dumps(payload, sort_keys=True)


class ParseErrorMockPolicyModel(Q5DeterministicMockPolicyModel):
    def generate(self, prompt: str) -> str:
        del prompt
        return "not-json"


def test_q5_fallback_taxonomy_is_closed_and_complete() -> None:
    assert {cause.value for cause in Q5FallbackCause} == {
        "policy_parse_error",
        "policy_model_error",
        "invalid_evidence_citation",
        "illegal_terminal_action",
        "premature_terminal_unresolved_state",
        "reauthorization_rejection",
        "observation_reauthorization_rejection",
        "tool_not_allowed",
        "tool_schema_invalid",
        "tool_new_entity_injection",
        "tool_forbidden_control_field",
        "duplicate_successful_observation",
        "terminal_only_observation_rejected",
        "observation_budget_exhausted",
        "step_budget_exhausted",
        "tool_invalid",
        "tool_timeout",
        "q4_rejection",
        "trusted_rule_policy_block",
    }


def test_q5_fallback_derivation_has_no_gold_or_semantic_inputs() -> None:
    source = inspect.getsource(derive_q5_v4_fallback_witness).lower()
    signature = inspect.signature(derive_q5_v4_fallback_witness)
    assert set(signature.parameters) == {
        "result",
        "policy_events",
        "tool_events",
        "trajectory",
        "terminal_event",
    }
    for forbidden in ("gold", "case_id", "stratum", "pair", "expected_action"):
        assert forbidden not in source


def test_q5_real_loop_q4_rejection_normalizes_and_verifies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_q4(proposal, report, budget):
        del proposal, report, budget
        return GovValidationResult(
            ok=False,
            reject_reason="insufficient_evidence_requires_escalation",
            forced_action=GovernanceAction.escalate_to_human,
        )

    monkeypatch.setattr(q5_loop_module, "validate_governance", reject_q4)
    monkeypatch.setattr(q5_fallback_module, "validate_governance", reject_q4)
    raw, gold_path = _pending_case_raw_run(
        tmp_path,
        run_id="q5-hr2-real-loop-q4-rejection",
        model=Q5DeterministicMockPolicyModel(),
    )
    graded = grade_q5_run(raw.run_dir, gold_path)

    assert verify_q5_graded_run(graded.run_dir, gold_path).protocol_version == "v4"
    for row in _jsonl(raw.results_path):
        assert row["fallback_reason"] == "q4_rejection"
        assert row["final_action"] == "escalate_to_human"
        assert row["disposition_source"] == "fallback"


@pytest.mark.parametrize(
    "mutation",
    [
        "model_human_review_to_fallback",
        "arbitrary_fallback_reason",
        "legal_cause_without_event",
        "transplanted_policy_error",
        "forged_policy_error",
        "forged_tool_failure",
        "forged_q4_rejection",
        "synchronized_all_ledgers_without_cause",
        "nonfallback_reason_injection",
        "deleted_causal_witness",
        "duplicated_causal_witness",
        "multiple_causal_witnesses",
    ],
)
@pytest.mark.parametrize("entrypoint", ["grade", "verify"])
def test_q5_v4_rehashed_fallback_causal_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
    entrypoint: str,
) -> None:
    genuine_fallback = mutation in {
        "arbitrary_fallback_reason",
        "deleted_causal_witness",
        "duplicated_causal_witness",
        "multiple_causal_witnesses",
    }
    raw, gold_path = _pending_case_raw_run(
        tmp_path,
        run_id=f"q5-hr2-{entrypoint}-{mutation}",
        model=(
            ParseErrorMockPolicyModel()
            if genuine_fallback
            else HumanReviewMockPolicyModel()
        ),
    )
    if entrypoint == "verify":
        grade_q5_run(raw.run_dir, gold_path)

    donor_dir: Path | None = None
    if mutation == "transplanted_policy_error":
        donor, _ = _pending_case_raw_run(
            tmp_path,
            run_id=f"q5-hr2-donor-{entrypoint}",
            model=ParseErrorMockPolicyModel(),
        )
        donor_dir = donor.run_dir
    _mutate_fallback_artifacts(raw.run_dir, mutation, donor_dir=donor_dir)

    with pytest.raises(ValueError):
        if entrypoint == "grade":
            grade_q5_run(raw.run_dir, gold_path)
        else:
            verify_q5_graded_run(raw.run_dir, gold_path)


def _mutate_fallback_artifacts(
    run_dir: Path,
    mutation: str,
    *,
    donor_dir: Path | None,
) -> None:
    filenames = (
        "results.jsonl",
        "policy_events.jsonl",
        "terminal_events.jsonl",
        "trajectory.jsonl",
        "tool_events.jsonl",
    )
    rows = {name: _jsonl(run_dir / name) for name in filenames}
    result = next(row for row in rows["results.jsonl"] if row["system"] == _LLM)
    terminal = next(
        row for row in rows["terminal_events.jsonl"] if row["system"] == _LLM
    )
    terminal_trajectory = next(
        row
        for row in rows["trajectory.jsonl"]
        if row["system"] == _LLM and row["event_type"] == "terminal"
    )
    terminal_policy = next(
        row
        for row in rows["policy_events.jsonl"]
        if row["system"] == _LLM
        and isinstance(row.get("accepted_proposal"), dict)
        and row["accepted_proposal"].get("kind") == "terminal"
    ) if any(
        row["system"] == _LLM
        and isinstance(row.get("accepted_proposal"), dict)
        and row["accepted_proposal"].get("kind") == "terminal"
        for row in rows["policy_events.jsonl"]
    ) else None

    if mutation in {
        "model_human_review_to_fallback",
        "legal_cause_without_event",
        "synchronized_all_ledgers_without_cause",
    }:
        cause = "policy_parse_error"
        _forge_fallback(
            result,
            terminal,
            terminal_trajectory,
            terminal_policy,
            cause=cause,
        )
        if mutation == "synchronized_all_ledgers_without_cause":
            terminal["q4_validation"] = {
                "ok": True,
                "reject_reason": None,
                "forced_action": None,
            }
    elif mutation == "arbitrary_fallback_reason":
        result["fallback_reason"] = "caller_supplied_but_unwitnessed"
    elif mutation == "nonfallback_reason_injection":
        result["fallback_reason"] = "policy_parse_error"
    elif mutation == "forged_policy_error":
        identity = {field: result[field] for field in ("case_id", "system", "run_index")}
        rows["trajectory.jsonl"].append(
            {
                **identity,
                "step_index": terminal_trajectory["step_index"],
                "context_version": terminal_trajectory["context_version"],
                "event_type": "policy_error",
                "policy_source": "llm",
                "reason_code": "policy_parse_error",
                "proposal_kind": None,
                "tool": None,
                "tool_status": None,
                "action": None,
                "policy_disposition": None,
                "disposition_source": None,
                "authorization_reason": None,
                "q4_validator_verdict": "not_run",
                "q4_validator_reject_reason": None,
            }
        )
    elif mutation == "forged_tool_failure":
        tool = next(row for row in rows["tool_events.jsonl"] if row["system"] == _LLM)
        tool["status"] = "timeout"
        tool["observation"] = None
        observation = next(
            row
            for row in rows["trajectory.jsonl"]
            if row["system"] == _LLM and row["event_type"] == "observation"
        )
        observation["tool_status"] = "timeout"
    elif mutation == "forged_q4_rejection":
        terminal["q4_validation"] = {
            "ok": False,
            "reject_reason": "insufficient_evidence_requires_escalation",
            "forced_action": "escalate_to_human",
        }
        terminal["q4_validation_input"]["report"]["evidence_decision"] = "insufficient"
    elif mutation == "transplanted_policy_error":
        assert donor_dir is not None
        donor_policy = next(
            row
            for row in _jsonl(donor_dir / "policy_events.jsonl")
            if row["system"] == _LLM and row["parse_status"] != "accepted"
        )
        donor_trajectory = next(
            row
            for row in _jsonl(donor_dir / "trajectory.jsonl")
            if row["system"] == _LLM and row["event_type"] == "policy_error"
        )
        identity = {field: result[field] for field in ("case_id", "system", "run_index")}
        rows["policy_events.jsonl"] = [
            row
            for row in rows["policy_events.jsonl"]
            if not (row["system"] == _LLM and row["step_index"] == donor_policy["step_index"])
        ]
        rows["policy_events.jsonl"].append({**donor_policy, **identity})
        rows["trajectory.jsonl"].append({**donor_trajectory, **identity})
        _forge_fallback(
            result,
            terminal,
            terminal_trajectory,
            terminal_policy,
            cause="policy_parse_error",
        )
    elif mutation == "deleted_causal_witness":
        rows["trajectory.jsonl"] = [
            row
            for row in rows["trajectory.jsonl"]
            if not (row["system"] == _LLM and row["event_type"] == "policy_error")
        ]
    elif mutation in {"duplicated_causal_witness", "multiple_causal_witnesses"}:
        witness = next(
            row
            for row in rows["trajectory.jsonl"]
            if row["system"] == _LLM and row["event_type"] == "policy_error"
        )
        duplicate = dict(witness)
        if mutation == "multiple_causal_witnesses":
            duplicate["event_type"] = "tool_rejected"
            duplicate["reason_code"] = "tool_schema_invalid"
        rows["trajectory.jsonl"].append(duplicate)
    else:  # pragma: no cover - mutation guard
        raise AssertionError(mutation)

    for name in filenames:
        _write_test_jsonl(run_dir / name, rows[name])
        _refresh_raw_hash(run_dir, name)
    if any(
        row["system"] == _LLM for row in rows["trajectory.jsonl"]
    ):
        _refresh_trajectory_result_hash(run_dir, _LLM)
    _refresh_row_counts(run_dir, rows)


def _forge_fallback(
    result: dict,
    terminal: dict,
    terminal_trajectory: dict,
    terminal_policy: dict | None,
    *,
    cause: str,
) -> None:
    proposal = terminal["terminal_proposal"]
    proposal["decision_basis"] = None
    proposal["disposition_source"] = "fallback"
    proposal["reason_code"] = cause
    result["policy_disposition"] = None
    result["disposition_source"] = "fallback"
    result["decision_basis_evidence_chunk_id"] = None
    result["decision_basis_observation_request_id"] = None
    result["fallback_reason"] = cause
    terminal_trajectory["policy_disposition"] = None
    terminal_trajectory["disposition_source"] = "fallback"
    terminal_trajectory["reason_code"] = cause
    if terminal_policy is not None:
        terminal_policy["accepted_proposal"] = json.loads(json.dumps(proposal))


def _refresh_row_counts(run_dir: Path, rows: dict[str, list[dict]]) -> None:
    manifest_path = run_dir / "manifest.json"
    manifest = _json(manifest_path)
    for name, artifact_rows in rows.items():
        manifest["artifact_row_counts"][name] = len(artifact_rows)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    hashes_path = run_dir / "hashes.json"
    hashes = _json(hashes_path)
    hashes["artifacts"]["manifest.json"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    hashes_path.write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
