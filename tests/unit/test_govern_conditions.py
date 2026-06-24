from __future__ import annotations

from typing import Any

from app.core.enums import DocumentStatus
from app.govern.conditions import (
    ActorContext,
    GovernanceAction,
    OpsCondition,
    detect_conditions,
)
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.schemas.retrieval import RetrievedChunk
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


def test_detect_permission_blocked_from_acl() -> None:
    blocked = make_retrieved_chunk("blocked", "restricted runbook")
    report = detect_conditions(
        _pass_result(reranked=[blocked], acl_blocked=[blocked]),
        ActorContext(role="editor"),
    )

    assert report.conditions == [OpsCondition.permission_blocked]
    assert report.authorized_actor is True
    assert report.permission_blocked_count == 1


def test_detect_permission_blocked_from_unauthorized() -> None:
    report = detect_conditions(
        _pass_result(),
        ActorContext(
            role="viewer",
            requested_action=GovernanceAction.open_remediation_ticket,
        ),
    )

    assert report.conditions == [OpsCondition.permission_blocked]
    assert report.authorized_actor is False
    assert report.permission_blocked_count == 1


def test_detect_active_active_conflict() -> None:
    left = make_retrieved_chunk(
        "left",
        "backup every 6h",
        doc_id="doc-a",
        conflict_group_id="backup-window",
    )
    right = make_retrieved_chunk(
        "right",
        "backup every 24h",
        doc_id="doc-b",
        conflict_group_id="backup-window",
        rank=2,
    )
    report = detect_conditions(
        _pass_result(reranked=[left, right], acl_surviving=[left, right]),
        ActorContext(role="admin"),
    )

    assert report.conditions == [OpsCondition.active_active_conflict]
    assert report.conflict_group_ids == ["backup-window"]


def test_detect_stale_procedure() -> None:
    stale = _with_signals(
        make_retrieved_chunk(
            "stale",
            "PodSecurityPolicy migration",
            doc_id="doc-psp",
            status=DocumentStatus.deprecated,
        ),
        superseded_by="active/pod-security-admission.md",
    )
    report = detect_conditions(
        _pass_result(reranked=[stale], deprecated=[stale]),
        ActorContext(role="editor"),
    )

    assert report.conditions == [OpsCondition.stale_procedure]
    assert report.stale_doc_ids == ["doc-psp"]


def test_detect_broken_xref() -> None:
    source = _with_signals(
        make_retrieved_chunk("source", "Step 2 references old rollback", doc_id="doc-upgrade"),
        overlay_relation_note={
            "type": "xref",
            "target_doc_id": "doc-rollback",
            "target_status": "deprecated",
        },
    )
    report = detect_conditions(
        _pass_result(reranked=[source], acl_surviving=[source]),
        ActorContext(role="editor"),
    )

    assert report.conditions == [OpsCondition.broken_xref]
    assert report.broken_xref_doc_ids == ["doc-rollback"]


def test_detect_config_violation() -> None:
    policy = make_retrieved_chunk(
        "policy",
        "restricted namespaces disallow privileged containers",
        doc_id="policy-restricted",
    )
    violating = _with_signals(
        make_retrieved_chunk(
            "violating",
            "securityContext.privileged=true",
            doc_id="doc-deploy",
            rank=2,
        ),
        policy_ref="policy-restricted",
        overlay_relation_note={
            "type": "violates_policy",
            "target_doc_id": "policy-restricted",
            "target_status": "active",
        },
    )
    report = detect_conditions(
        _pass_result(reranked=[policy, violating], acl_surviving=[policy, violating]),
        ActorContext(role="admin"),
    )

    assert report.conditions == [OpsCondition.config_violation]
    assert report.violating_doc_ids == ["doc-deploy"]


def test_detect_insufficient_evidence() -> None:
    report = detect_conditions(
        _pass_result(evidence_sufficient=False),
        ActorContext(role="admin"),
    )

    assert report.conditions == [OpsCondition.insufficient_evidence]
    assert report.evidence_decision == "insufficient"


def test_detect_no_condition_is_noop() -> None:
    clean = make_retrieved_chunk("clean", "current rollout guidance")
    report = detect_conditions(
        _pass_result(reranked=[clean], acl_surviving=[clean]),
        ActorContext(role="editor"),
    )

    assert report.conditions == []
    assert report.evidence_decision == "sufficient"
    assert report.authorized_actor is True


def test_detect_multi_condition() -> None:
    stale = _with_signals(
        make_retrieved_chunk(
            "stale",
            "old procedure",
            doc_id="doc-old",
            status=DocumentStatus.deprecated,
        ),
        superseded_by="active/new.md",
    )
    left = make_retrieved_chunk(
        "left",
        "backup 6h",
        doc_id="doc-a",
        conflict_group_id="conflict-1",
        rank=2,
    )
    right = make_retrieved_chunk(
        "right",
        "backup 24h",
        doc_id="doc-b",
        conflict_group_id="conflict-1",
        rank=3,
    )
    report = detect_conditions(
        _pass_result(
            reranked=[stale, left, right],
            acl_surviving=[left, right],
            deprecated=[stale],
        ),
        ActorContext(role="admin"),
    )

    assert OpsCondition.stale_procedure in report.conditions
    assert OpsCondition.active_active_conflict in report.conditions
    assert report.stale_doc_ids == ["doc-old"]
    assert report.conflict_group_ids == ["conflict-1"]


def test_authorized_roles_override() -> None:
    report = detect_conditions(
        _pass_result(),
        ActorContext(
            role="viewer",
            requested_action=GovernanceAction.open_remediation_ticket,
        ),
        authorized_roles={
            GovernanceAction.open_remediation_ticket: frozenset({"viewer"}),
        },
    )

    assert report.conditions == []
    assert report.authorized_actor is True


def _pass_result(
    *,
    reranked: list[RetrievedChunk] | None = None,
    acl_surviving: list[RetrievedChunk] | None = None,
    acl_blocked: list[RetrievedChunk] | None = None,
    deprecated: list[RetrievedChunk] | None = None,
    evidence_sufficient: bool = True,
) -> RetrievalPassResult:
    reranked = reranked or []
    return RetrievalPassResult(
        query="test query",
        retrieved_chunks=reranked,
        reranked_chunks=reranked,
        state_decision=StateGateDecision(
            surviving_chunks=[
                item for item in reranked if item.chunk.status == DocumentStatus.active
            ],
            deprecated_chunks=deprecated or [],
        ),
        acl_decision=ACLGateDecision(
            surviving_chunks=acl_surviving or [],
            blocked_chunks=acl_blocked or [],
        ),
        conflict_decision=ConflictDecision(),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=evidence_sufficient,
            reason="sufficient" if evidence_sufficient else "test_insufficient",
            support_count=len(acl_surviving or reranked),
            entity_miss=not evidence_sufficient,
        ),
    )


def _with_signals(result: RetrievedChunk, **signals: Any) -> RetrievedChunk:
    return result.model_copy(update={"chunk": result.chunk.model_copy(update=signals)})
