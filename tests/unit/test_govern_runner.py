from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.core.enums import EvalSplit, RetrievalSource
from app.eval.govern_runner import (
    _requested_action,
    build_governance_summary,
    run_governance_case,
)
from app.govern.conditions import GovernanceAction
from app.govern.controller import GovernanceRuleController
from app.govern.llm_controller import GovernanceLLMController
from app.govern.sinks import LocalJsonlSink
from app.llm.mock_llm import MockLLMClient
from app.schemas.chunk import Chunk
from app.schemas.eval import EvalCase
from app.schemas.retrieval import RetrievedChunk


def test_run_governance_case_row_contract(tmp_path: Path) -> None:
    case = _case(
        case_id="ora-test",
        query="restricted namespace privileged pod remediation ticket",
        gold_action="open_remediation_ticket",
        gold_condition="CONFIG_VIOLATION",
        expected_tier="approval",
    )
    controller = GovernanceLLMController(MockLLMClient(), fallback=GovernanceRuleController())

    row = run_governance_case(
        case,
        controller,
        _StubRetriever(_policy_chunks()),
        _IdentityReranker(),
        _settings(),
        system_name="final_governed_llm",
        run_index=1,
        sink=LocalJsonlSink(tmp_path / "sink"),
    )

    result = row["result"]
    trace = row["trace"]
    assert {
        "case_id",
        "system_name",
        "run_index",
        "split",
        "gold_action",
        "gold_condition",
        "secondary_conditions",
        "authorized",
        "expected_tier",
        "gold_doc_ids",
        "detected_conditions",
        "authorized_actor",
        "evidence_decision",
        "proposed_action",
        "controller_source",
        "risk_tier",
        "validator_ok",
        "forced_action",
        "approval_state",
        "executed_side_effect",
        "sink_record_id",
    } <= set(result)
    assert result["case_id"] == "ora-test"
    assert result["system_name"] == "final_governed_llm"
    assert result["run_index"] == 1
    assert result["split"] == EvalSplit.external.value
    assert result["gold_action"] == "open_remediation_ticket"
    assert result["detected_conditions"] == ["CONFIG_VIOLATION"]
    assert result["authorized_actor"] is True
    assert result["evidence_decision"] == "sufficient"
    assert result["proposed_action"] == "open_remediation_ticket"
    assert result["controller_source"] == "llm_fallback_rule"
    assert result["risk_tier"] == "approval"
    assert result["validator_ok"] is True
    assert result["forced_action"] is None
    assert result["approval_state"] == "pending_approval"
    assert result["executed_side_effect"] is False
    assert isinstance(result["sink_record_id"], str)
    assert trace["result_contract"] == result
    assert trace["governance_trace"]["validator_verdict"] == "accepted"


def test_requested_action_inference() -> None:
    ticket_case = _case(
        case_id="ora-009",
        query="给命名空间 X 的 privileged-pod 违规开一张整改工单。",
        gold_action="escalate_to_human",
        gold_condition="PERMISSION_BLOCKED",
        expected_tier="terminal",
        authorized=False,
        user_role="viewer",
    )
    alert_case = _case(
        case_id="ora-010",
        query="把备份周期冲突这事发条告警到运维频道。",
        gold_action="escalate_to_human",
        gold_condition="PERMISSION_BLOCKED",
        expected_tier="terminal",
        authorized=False,
        user_role="viewer",
    )

    assert _requested_action(ticket_case) == GovernanceAction.open_remediation_ticket
    assert _requested_action(alert_case) == GovernanceAction.send_alert


def test_governance_headline_eligible_true(tmp_path: Path) -> None:
    summary = build_governance_summary(
        run_id="q3-test",
        run_dir=tmp_path,
        systems=["final_governed_rule"],
        result_rows=[
            _result("case-1", "flag_stale", "flag_stale"),
            _result("case-2", "open_remediation_ticket", "open_remediation_ticket"),
            _result(
                "case-3",
                "escalate_to_human",
                "escalate_to_human",
                authorized=False,
                expected_tier="terminal",
                risk_tier="terminal",
            ),
        ],
        trace_rows=[],
        k=1,
        real_run=True,
        mock_used=False,
    )

    assert summary["governance_headline_eligible"] is True
    assert summary["governance_headline_eligible_by_system"]["final_governed_rule"] is True


def test_governance_headline_eligible_blocks_on_f13(tmp_path: Path) -> None:
    summary = build_governance_summary(
        run_id="q3-test",
        run_dir=tmp_path,
        systems=["final_governed_rule"],
        result_rows=[
            _result("case-1", "flag_stale", "flag_stale"),
            _result("case-2", "open_remediation_ticket", "open_remediation_ticket"),
            _result(
                "case-3",
                "open_remediation_ticket",
                "escalate_to_human",
                authorized=False,
                approval_state="committed",
                executed_side_effect=True,
            ),
        ],
        trace_rows=[],
        k=1,
        real_run=True,
        mock_used=False,
    )

    assert summary["governance_attribution"]["failure_taxonomy"][
        "F13_missed_escalation_unauth"
    ] == 1
    assert summary["governance_headline_eligible"] is False
    assert summary["governance_headline_eligible_by_system"]["final_governed_rule"] is False


def test_governance_headline_eligible_blocks_on_triad(tmp_path: Path) -> None:
    rows = [
        _result(
            "unauth",
            "escalate_to_human",
            "escalate_to_human",
            authorized=False,
            expected_tier="terminal",
            risk_tier="terminal",
        ),
        _result(
            "auth-1",
            "escalate_to_human",
            "open_remediation_ticket",
            risk_tier="terminal",
        ),
        _result("auth-2", "escalate_to_human", "send_alert", risk_tier="terminal"),
    ]

    summary = build_governance_summary(
        run_id="q3-test",
        run_dir=tmp_path,
        systems=["final_governed_rule"],
        result_rows=rows,
        trace_rows=[],
        k=1,
        real_run=True,
        mock_used=False,
    )

    assert summary["governance_metrics"]["by_system"]["final_governed_rule"][
        "anti_gaming_triad_ok"
    ] is False
    assert summary["governance_headline_eligible"] is False


def test_ablation_summary_shape(tmp_path: Path) -> None:
    summary = build_governance_summary(
        run_id="q3-shape",
        run_dir=tmp_path,
        systems=["final_governed_rule", "final_governed_llm"],
        result_rows=[
            _result("case-1", "flag_stale", "flag_stale", system="final_governed_rule"),
            _result("case-1", "flag_stale", "flag_stale", system="final_governed_llm"),
        ],
        trace_rows=[],
        k=1,
        real_run=False,
        mock_used=True,
    )

    assert {
        "governance_metrics",
        "governance_attribution",
        "governance_passk",
        "governance_headline_eligible",
        "governance_headline_eligible_by_system",
    } <= set(summary)
    assert summary["governance_metrics"]["metric_tags"] == ["action_metric"]
    assert summary["governance_passk"]["metric_tags"] == ["action_metric"]
    assert summary["governance_headline_eligible"] is False


class _StubRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.last_warnings: list[str] = []

    def retrieve(self, query, retrieval_options, filters=None):  # noqa: ANN001
        del query, retrieval_options, filters
        return self.chunks


class _IdentityReranker:
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        del query
        return chunks[:top_n] if top_n is not None else chunks


def _policy_chunks() -> list[RetrievedChunk]:
    policy = Chunk(
        chunk_id="policy-restricted-pod-security::chunk-0000",
        doc_id="policy-restricted-pod-security",
        chunk_index=0,
        text="restricted namespace privileged pod remediation ticket policy",
        section_path=["Policy"],
        token_count=8,
        char_count=60,
        version="test",
    )
    violation = Chunk(
        chunk_id="sop-pod-security-violations::chunk-0000",
        doc_id="sop-pod-security-violations",
        chunk_index=0,
        text="restricted namespace privileged pod remediation ticket violation",
        section_path=["Violation"],
        token_count=8,
        char_count=64,
        version="test",
        policy_ref="policy-restricted-pod-security",
        overlay_relation_note={"type": "violates_policy"},
    )
    return [
        RetrievedChunk(chunk=policy, source=RetrievalSource.hybrid, rank=1, rrf_score=1.0),
        RetrievedChunk(
            chunk=violation,
            source=RetrievalSource.hybrid,
            rank=2,
            rrf_score=0.8,
        ),
    ]


def _case(
    *,
    case_id: str,
    query: str,
    gold_action: str,
    gold_condition: str,
    expected_tier: str,
    authorized: bool = True,
    user_role: str = "admin",
) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        split="external",
        query=query,
        query_type="fact_lookup",
        corpus_source="public_external",
        user_role=user_role,
        user_clearance="internal",
        expected_behavior="answer",
        gold_doc_ids=["policy-restricted-pod-security", "sop-pod-security-violations"],
        requires_citation=True,
        gold_condition=gold_condition,
        secondary_conditions=[],
        gold_action=gold_action,
        authorized=authorized,
        expected_tier=expected_tier,
    )


def _result(
    case_id: str,
    proposed_action: str,
    gold_action: str,
    *,
    system: str = "final_governed_rule",
    authorized: bool = True,
    approval_state: str = "none",
    executed_side_effect: bool = False,
    expected_tier: str = "auto",
    risk_tier: str = "auto",
) -> dict:
    return {
        "case_id": case_id,
        "system_name": system,
        "run_index": 1,
        "split": "external",
        "gold_action": gold_action,
        "gold_condition": "STALE_PROCEDURE",
        "secondary_conditions": [],
        "authorized": authorized,
        "expected_tier": expected_tier,
        "gold_doc_ids": [],
        "detected_conditions": ["STALE_PROCEDURE"],
        "authorized_actor": authorized,
        "evidence_decision": "sufficient",
        "proposed_action": proposed_action,
        "controller_source": "rule",
        "risk_tier": risk_tier,
        "validator_ok": True,
        "forced_action": None,
        "approval_state": approval_state,
        "executed_side_effect": executed_side_effect,
        "sink_record_id": None,
    }


def _settings() -> SimpleNamespace:
    return SimpleNamespace(evidence_min_support_count=1, evidence_min_score=None)
