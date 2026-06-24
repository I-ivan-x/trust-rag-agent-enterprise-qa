from __future__ import annotations

from pathlib import Path

from app.govern.approvals import approve_pending, list_pending, reject_pending
from app.govern.conditions import (
    ActorContext,
    ConditionReport,
    GovernanceAction,
    OpsCondition,
)
from app.govern.governor import govern
from app.govern.sinks import LocalJsonlSink
from app.govern.validator import (
    GovernanceBudget,
    GovernanceProposal,
    validate_governance,
)
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


def test_legal_action_passes() -> None:
    result = validate_governance(
        _proposal(GovernanceAction.open_remediation_ticket),
        _report(OpsCondition.config_violation),
        GovernanceBudget(),
    )

    assert result.ok is True
    assert result.forced_action is None


def test_illegal_action_forced_escalate() -> None:
    result = validate_governance(
        _proposal(GovernanceAction.send_alert),
        _report(OpsCondition.stale_procedure),
        GovernanceBudget(),
    )

    assert result.ok is False
    assert result.reject_reason == "action_not_legal_for_conditions"
    assert result.forced_action == GovernanceAction.escalate_to_human


def test_unauthorized_forced_escalate() -> None:
    result = validate_governance(
        _proposal(GovernanceAction.open_remediation_ticket),
        _report(OpsCondition.config_violation, authorized_actor=False),
        GovernanceBudget(),
    )

    assert result.ok is False
    assert result.reject_reason == "unauthorized_requires_escalation"
    assert result.forced_action == GovernanceAction.escalate_to_human


def test_insufficient_evidence_forced_escalate() -> None:
    result = validate_governance(
        _proposal(GovernanceAction.flag_stale),
        _report(OpsCondition.stale_procedure, evidence_decision="insufficient"),
        GovernanceBudget(),
    )

    assert result.ok is False
    assert result.reject_reason == "insufficient_evidence_requires_escalation"
    assert result.forced_action == GovernanceAction.escalate_to_human


def test_permission_blocked_only_escalate() -> None:
    blocked = _report(OpsCondition.permission_blocked, authorized_actor=False)

    rejected = validate_governance(
        _proposal(GovernanceAction.open_remediation_ticket),
        blocked,
        GovernanceBudget(),
    )
    accepted = validate_governance(
        _proposal(GovernanceAction.escalate_to_human),
        blocked,
        GovernanceBudget(),
    )

    assert rejected.ok is False
    assert rejected.forced_action == GovernanceAction.escalate_to_human
    assert accepted.ok is True


def test_budget_exhausted_rejects() -> None:
    result = validate_governance(
        _proposal(GovernanceAction.flag_stale),
        _report(OpsCondition.stale_procedure),
        GovernanceBudget(max_actions=3, consumed=3),
    )

    assert result.ok is False
    assert result.reject_reason == "budget_exhausted"
    assert result.forced_action == GovernanceAction.escalate_to_human


def test_risk_tier_from_table_not_proposal() -> None:
    proposal = _proposal(
        GovernanceAction.open_remediation_ticket,
        args={"risk_tier": "auto", "risk": "auto"},
    )

    result = validate_governance(
        proposal,
        _report(OpsCondition.config_violation),
        GovernanceBudget(),
    )

    assert result.ok is True


def test_govern_no_op_when_no_condition(tmp_path: Path) -> None:
    outcome = govern(
        _report(None),
        _pass_result(),
        ActorContext(role="admin"),
        _Controller(GovernanceAction.no_op),
        LocalJsonlSink(tmp_path),
    )

    assert outcome.proposal.action == GovernanceAction.no_op
    assert outcome.record is None
    assert outcome.trace["validator_verdict"] == "no_op"
    assert outcome.trace["sink_record_id"] is None


def test_govern_auto_commits(tmp_path: Path) -> None:
    outcome = govern(
        _report(OpsCondition.stale_procedure, stale_doc_ids=["doc-a"]),
        _pass_result(),
        ActorContext(role="editor"),
        _Controller(GovernanceAction.flag_stale),
        LocalJsonlSink(tmp_path),
    )

    assert outcome.record is not None
    assert outcome.record.action == GovernanceAction.flag_stale
    assert outcome.record.approval_state == "committed"
    assert outcome.trace["risk_tier"] == "auto"


def test_govern_approval_pending(tmp_path: Path) -> None:
    outcome = govern(
        _report(OpsCondition.config_violation, violating_doc_ids=["doc-a"]),
        _pass_result(),
        ActorContext(role="admin"),
        _Controller(GovernanceAction.open_remediation_ticket),
        LocalJsonlSink(tmp_path),
    )

    assert outcome.record is not None
    assert outcome.record.action == GovernanceAction.open_remediation_ticket
    assert outcome.record.approval_state == "pending_approval"
    assert outcome.trace["approval_state"] == "pending_approval"


def test_govern_terminal_escalates(tmp_path: Path) -> None:
    outcome = govern(
        _report(OpsCondition.permission_blocked, authorized_actor=False),
        _pass_result(),
        ActorContext(role="viewer"),
        _Controller(GovernanceAction.escalate_to_human),
        LocalJsonlSink(tmp_path),
    )

    assert outcome.record is not None
    assert outcome.record.action == GovernanceAction.escalate_to_human
    assert outcome.record.approval_state == "escalated"
    assert outcome.trace["risk_tier"] == "terminal"


def test_approve_pending_commits(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path)
    outcome = govern(
        _report(OpsCondition.config_violation, violating_doc_ids=["doc-a"]),
        _pass_result(),
        ActorContext(role="admin"),
        _Controller(GovernanceAction.open_remediation_ticket),
        sink,
    )

    pending = list_pending(sink)
    approved = approve_pending(outcome.record.record_id, sink)  # type: ignore[union-attr]

    assert [record.record_id for record in pending] == [outcome.record.record_id]
    assert approved.approval_state == "committed"
    assert list_pending(sink) == []


def test_reject_pending_drops(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path)
    outcome = govern(
        _report(OpsCondition.config_violation, violating_doc_ids=["doc-a"]),
        _pass_result(),
        ActorContext(role="admin"),
        _Controller(GovernanceAction.open_remediation_ticket),
        sink,
    )

    rejected = reject_pending(outcome.record.record_id, sink)  # type: ignore[union-attr]

    assert rejected.approval_state == "dropped"
    assert list_pending(sink) == []


def _proposal(
    action: GovernanceAction,
    *,
    args: dict | None = None,
) -> GovernanceProposal:
    return GovernanceProposal(action=action, args=args or {}, source="test")


class _Controller:
    controller_source = "test"

    def __init__(self, action: GovernanceAction) -> None:
        self.action = action

    def select(self, report, context) -> GovernanceProposal:
        del report
        args = {"evidence_citations": context.evidence_citations}
        return GovernanceProposal(
            action=self.action,
            args=args,
            source="test",
            controller_source=self.controller_source,
        )


def _report(
    condition: OpsCondition | None,
    *,
    authorized_actor: bool = True,
    evidence_decision: str = "sufficient",
    stale_doc_ids: list[str] | None = None,
    violating_doc_ids: list[str] | None = None,
) -> ConditionReport:
    return ConditionReport(
        conditions=[condition] if condition is not None else [],
        authorized_actor=authorized_actor,
        evidence_decision=evidence_decision,
        stale_doc_ids=stale_doc_ids or [],
        violating_doc_ids=violating_doc_ids or [],
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
