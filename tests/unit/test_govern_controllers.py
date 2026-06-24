from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.govern.conditions import (
    ActorContext,
    ConditionReport,
    GovernanceAction,
    OpsCondition,
)
from app.govern.controller import GovernanceControllerContext, GovernanceRuleController
from app.govern.governor import govern
from app.govern.llm_controller import GovernanceLLMController
from app.govern.sinks import LocalJsonlSink
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


def test_rule_no_op_when_clean() -> None:
    proposal = GovernanceRuleController().select(
        _report(),
        _context(),
    )

    assert proposal.action == GovernanceAction.no_op
    assert proposal.source == "rule"


def test_rule_conflict_to_alert() -> None:
    proposal = GovernanceRuleController().select(
        _report(OpsCondition.active_active_conflict, conflict_group_ids=["g1"]),
        _context(conflict_doc_ids=["doc-a", "doc-b"]),
    )

    assert proposal.action == GovernanceAction.send_alert
    assert proposal.args["doc_ids"] == ["doc-a", "doc-b"]


def test_rule_config_to_ticket() -> None:
    proposal = GovernanceRuleController().select(
        _report(OpsCondition.config_violation, violating_doc_ids=["doc-a"]),
        _context(doc_ids=["doc-a"]),
    )

    assert proposal.action == GovernanceAction.open_remediation_ticket
    assert proposal.args["doc_ids"] == ["doc-a"]


def test_rule_stale_to_flag() -> None:
    proposal = GovernanceRuleController().select(
        _report(OpsCondition.stale_procedure, stale_doc_ids=["doc-old"]),
        _context(doc_ids=["doc-old"]),
    )

    assert proposal.action == GovernanceAction.flag_stale
    assert proposal.args["stale_doc_ids"] == ["doc-old"]


def test_rule_unauthorized_to_escalate() -> None:
    proposal = GovernanceRuleController().select(
        _report(OpsCondition.config_violation, authorized_actor=False),
        _context(),
    )

    assert proposal.action == GovernanceAction.escalate_to_human
    assert proposal.args["reason"] == "permission_blocked"


def test_rule_multi_condition_priority() -> None:
    proposal = GovernanceRuleController().select(
        _report(
            OpsCondition.permission_blocked,
            OpsCondition.stale_procedure,
            authorized_actor=False,
        ),
        _context(),
    )

    assert proposal.action == GovernanceAction.escalate_to_human
    assert proposal.args["reason"] == "permission_blocked"


def test_rule_args_citations_context_only() -> None:
    context = _context(citations=["chunk-a", "chunk-b"])

    ticket = GovernanceRuleController().select(
        _report(OpsCondition.config_violation),
        context,
    )
    alert = GovernanceRuleController().select(
        _report(OpsCondition.active_active_conflict, conflict_group_ids=["g1"]),
        context,
    )

    context_ids = {item["chunk_id"] for item in context.neighborhood}
    assert set(ticket.args["evidence_citations"]) <= context_ids
    assert set(alert.args["evidence_citations"]) <= context_ids


def test_llm_valid_proposal_accepted() -> None:
    llm = _FakeGovernanceLLM(
        {
            "action": "open_remediation_ticket",
            "args": {"doc_ids": ["doc-a"], "evidence_citations": ["chunk-a"]},
            "reason": "Open a remediation ticket.",
        }
    )

    proposal = GovernanceLLMController(llm).select(
        _report(OpsCondition.config_violation),
        _context(),
    )

    assert proposal.action == GovernanceAction.open_remediation_ticket
    assert proposal.source == "llm"
    assert proposal.accepted is True
    assert proposal.fallback_reason is None
    assert llm.temperatures == [0]


def test_llm_parse_error_falls_back() -> None:
    proposal = GovernanceLLMController(_FakeGovernanceLLM("not json")).select(
        _report(OpsCondition.config_violation),
        _context(),
    )

    assert proposal.action == GovernanceAction.open_remediation_ticket
    assert proposal.source == "llm_fallback_rule"
    assert proposal.accepted is False
    assert proposal.fallback_reason == "parse_error"


def test_llm_illegal_action_falls_back() -> None:
    proposal = GovernanceLLMController(
        _FakeGovernanceLLM({"action": "send_alert", "args": {}, "reason": "Bad."})
    ).select(
        _report(OpsCondition.stale_procedure, stale_doc_ids=["doc-old"]),
        _context(),
    )

    assert proposal.action == GovernanceAction.flag_stale
    assert proposal.source == "llm_fallback_rule"
    assert proposal.accepted is False
    assert proposal.fallback_reason == "illegal_action"


def test_llm_cannot_self_downgrade_risk(tmp_path: Path) -> None:
    llm = _FakeGovernanceLLM(
        {
            "action": "open_remediation_ticket",
            "args": {"evidence_citations": ["chunk-a"]},
            "reason": "Ticket it.",
            "risk": "auto",
        }
    )

    outcome = govern(
        _report(OpsCondition.config_violation, violating_doc_ids=["doc-a"]),
        _pass_result(),
        ActorContext(role="admin"),
        GovernanceLLMController(llm),
        LocalJsonlSink(tmp_path),
    )

    assert outcome.proposal.action == GovernanceAction.open_remediation_ticket
    assert outcome.record is not None
    assert outcome.record.risk_tier.value == "approval"
    assert outcome.record.approval_state == "pending_approval"
    assert outcome.trace["risk_tier"] == "approval"


def test_llm_unauthorized_still_escalated(tmp_path: Path) -> None:
    llm = _FakeGovernanceLLM(
        {
            "action": "open_remediation_ticket",
            "args": {"evidence_citations": ["chunk-a"]},
            "reason": "Ticket it.",
        }
    )

    outcome = govern(
        _report(
            OpsCondition.config_violation,
            authorized_actor=False,
            violating_doc_ids=["doc-a"],
        ),
        _pass_result(),
        ActorContext(role="viewer"),
        GovernanceLLMController(llm),
        LocalJsonlSink(tmp_path),
    )

    assert outcome.validation.ok is False
    assert outcome.validation.reject_reason == "unauthorized_requires_escalation"
    assert outcome.record is not None
    assert outcome.record.action == GovernanceAction.escalate_to_human
    assert outcome.record.approval_state == "escalated"
    assert outcome.trace["forced"] is True


def _report(
    *conditions: OpsCondition,
    authorized_actor: bool = True,
    stale_doc_ids: list[str] | None = None,
    violating_doc_ids: list[str] | None = None,
    conflict_group_ids: list[str] | None = None,
) -> ConditionReport:
    return ConditionReport(
        conditions=list(conditions),
        authorized_actor=authorized_actor,
        evidence_decision="sufficient",
        stale_doc_ids=stale_doc_ids or [],
        violating_doc_ids=violating_doc_ids or [],
        conflict_group_ids=conflict_group_ids or [],
    )


def _context(
    *,
    doc_ids: list[str] | None = None,
    conflict_doc_ids: list[str] | None = None,
    citations: list[str] | None = None,
) -> GovernanceControllerContext:
    doc_ids = doc_ids or ["doc-a"]
    citations = citations or ["chunk-a"]
    return GovernanceControllerContext(
        query="test query",
        neighborhood=[
            {"chunk_id": "chunk-a", "doc_id": "doc-a", "status": "active"},
            {"chunk_id": "chunk-b", "doc_id": "doc-b", "status": "active"},
        ],
        evidence_citations=citations,
        doc_ids=doc_ids,
        conflict_doc_ids=conflict_doc_ids or [],
    )


def _pass_result() -> RetrievalPassResult:
    chunk = make_retrieved_chunk("chunk-a", "current context", doc_id="doc-a")
    return RetrievalPassResult(
        query="test query",
        retrieved_chunks=[chunk],
        reranked_chunks=[chunk],
        state_decision=StateGateDecision(surviving_chunks=[chunk]),
        acl_decision=ACLGateDecision(surviving_chunks=[chunk]),
        conflict_decision=ConflictDecision(),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=True,
            reason="sufficient",
            support_count=1,
        ),
    )


class _FakeGovernanceLLM:
    def __init__(self, response: dict[str, Any] | str) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.temperatures: list[float | int | None] = []

    def generate(self, prompt: str, *, temperature: float | int | None = None) -> str:
        self.prompts.append(prompt)
        self.temperatures.append(temperature)
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response)
