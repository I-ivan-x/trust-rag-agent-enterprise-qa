from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.govern.conditions import (
    ActorContext,
    ConditionReport,
    GovernanceAction,
    OpsCondition,
)
from app.govern.executor import execute_governance_action
from app.govern.mcp_server import RunbookOpsMCPTools
from app.govern.sinks import LocalJsonlSink
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


def test_create_ticket_writes_record(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path)

    record = sink.create_ticket(
        condition=OpsCondition.config_violation,
        doc_ids=["doc-a"],
        evidence_citations=["chunk-a"],
        actor_role="admin",
    )

    rows = _read_jsonl(tmp_path / "tickets.jsonl")
    assert len(rows) == 1
    assert rows[0]["record_id"] == record.record_id
    assert rows[0]["action"] == GovernanceAction.open_remediation_ticket.value
    assert rows[0]["condition"] == OpsCondition.config_violation.value
    assert rows[0]["approval_state"] == "pending_approval"
    assert rows[0]["risk_tier"] == "approval"


def test_send_alert_is_broadcast_only(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path)

    sink.send_alert(
        condition=OpsCondition.active_active_conflict,
        doc_ids=["doc-a", "doc-b"],
        evidence_citations=["chunk-a", "chunk-b"],
        actor_role="admin",
    )

    record = _read_jsonl(tmp_path / "alerts.jsonl")[0]
    assert record["action"] == GovernanceAction.send_alert.value
    assert record["approval_state"] == "pending_approval"
    assert "assignee" not in record
    assert "owner" not in record


def test_flag_document_committed(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path)

    record = sink.flag_document(
        condition=OpsCondition.stale_procedure,
        doc_ids=["doc-stale"],
        evidence_citations=["chunk-stale"],
        actor_role="editor",
    )

    assert record.approval_state == "committed"
    assert _read_jsonl(tmp_path / "annotations.jsonl")[0]["risk_tier"] == "auto"


def test_escalate_writes_escalation(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path)

    record = sink.escalate(
        condition=OpsCondition.insufficient_evidence,
        doc_ids=[],
        evidence_citations=[],
        actor_role="viewer",
    )

    rows = _read_jsonl(tmp_path / "escalations.jsonl")
    assert rows[0]["record_id"] == record.record_id
    assert rows[0]["approval_state"] == "escalated"
    assert rows[0]["risk_tier"] == "terminal"


def test_dedup_idempotent(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path)

    first = sink.create_ticket(
        condition=OpsCondition.config_violation,
        doc_ids=["doc-b", "doc-a"],
        evidence_citations=["chunk-a"],
        actor_role="admin",
    )
    second = sink.create_ticket(
        condition=OpsCondition.config_violation,
        doc_ids=["doc-a", "doc-b"],
        evidence_citations=["chunk-a"],
        actor_role="admin",
    )

    assert second.record_id == first.record_id
    assert len(_read_jsonl(tmp_path / "tickets.jsonl")) == 1


def test_executor_risk_tier_mapping(tmp_path: Path) -> None:
    pass_result = _pass_result()
    actor = ActorContext(role="admin")

    flag = execute_governance_action(
        GovernanceAction.flag_stale,
        _report(OpsCondition.stale_procedure, stale_doc_ids=["doc-a"]),
        pass_result,
        actor,
        LocalJsonlSink(tmp_path / "flag"),
    )
    ticket = execute_governance_action(
        GovernanceAction.open_remediation_ticket,
        _report(OpsCondition.config_violation, violating_doc_ids=["doc-a"]),
        pass_result,
        actor,
        LocalJsonlSink(tmp_path / "ticket"),
    )
    alert = execute_governance_action(
        GovernanceAction.send_alert,
        _report(OpsCondition.active_active_conflict),
        _pass_result(conflict=True),
        actor,
        LocalJsonlSink(tmp_path / "alert"),
    )
    escalated = execute_governance_action(
        GovernanceAction.escalate_to_human,
        _report(OpsCondition.permission_blocked),
        pass_result,
        actor,
        LocalJsonlSink(tmp_path / "escalate"),
    )

    assert flag.approval_state == "committed"
    assert ticket.approval_state == "pending_approval"
    assert alert.approval_state == "pending_approval"
    assert escalated.approval_state == "escalated"


def test_mcp_server_tool_roundtrip(tmp_path: Path) -> None:
    tools = RunbookOpsMCPTools(LocalJsonlSink(tmp_path))

    payload = tools.create_ticket(
        OpsCondition.config_violation.value,
        ["doc-a"],
        ["chunk-a"],
        "admin",
    )

    assert payload["action"] == GovernanceAction.open_remediation_ticket.value
    assert _read_jsonl(tmp_path / "tickets.jsonl")[0]["record_id"] == payload["record_id"]


def test_evidence_citations_context_only(tmp_path: Path) -> None:
    pass_result = _pass_result()
    sink = LocalJsonlSink(tmp_path)

    with pytest.raises(ValueError, match="not in context"):
        execute_governance_action(
            GovernanceAction.flag_stale,
            _report(OpsCondition.stale_procedure, stale_doc_ids=["doc-a"]),
            pass_result,
            ActorContext(role="admin"),
            sink,
            evidence_citations=["chunk-outside"],
        )

    record = execute_governance_action(
        GovernanceAction.flag_stale,
        _report(OpsCondition.stale_procedure, stale_doc_ids=["doc-a"]),
        pass_result,
        ActorContext(role="admin"),
        sink,
        evidence_citations=["chunk-a"],
    )
    assert record.evidence_citations == ["chunk-a"]


def _report(
    condition: OpsCondition,
    *,
    stale_doc_ids: list[str] | None = None,
    violating_doc_ids: list[str] | None = None,
) -> ConditionReport:
    return ConditionReport(
        conditions=[condition],
        authorized_actor=True,
        evidence_decision="sufficient",
        stale_doc_ids=stale_doc_ids or [],
        violating_doc_ids=violating_doc_ids or [],
    )


def _pass_result(*, conflict: bool = False) -> RetrievalPassResult:
    first = make_retrieved_chunk(
        "chunk-a",
        "current context",
        doc_id="doc-a",
        conflict_group_id="conflict-1" if conflict else None,
    )
    second = make_retrieved_chunk(
        "chunk-b",
        "conflicting context",
        doc_id="doc-b",
        conflict_group_id="conflict-1",
        rank=2,
    )
    reranked = [first, second] if conflict else [first]
    return RetrievalPassResult(
        query="test query",
        retrieved_chunks=reranked,
        reranked_chunks=reranked,
        state_decision=StateGateDecision(surviving_chunks=reranked),
        acl_decision=ACLGateDecision(surviving_chunks=reranked),
        conflict_decision=ConflictDecision(
            has_conflict=conflict,
            conflict_group_id="conflict-1" if conflict else None,
            conflicting_chunks=reranked if conflict else [],
        ),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=True,
            reason="sufficient",
            support_count=len(reranked),
        ),
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
