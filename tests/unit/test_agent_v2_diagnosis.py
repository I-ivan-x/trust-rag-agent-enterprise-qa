from __future__ import annotations

from app.agent.diagnosis import ActionType, FailureType, diagnose
from app.core.enums import AccessLevel, DocumentStatus
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


def test_diagnosis_sufficient_has_no_recovery_actions() -> None:
    active = make_retrieved_chunk("active", "refresh token limit")
    report = diagnose(
        _pass_result(
            reranked=[active],
            acl_surviving=[active],
            evidence_sufficient=True,
            support_count=1,
        )
    )

    assert report.evidence_decision == "sufficient"
    assert report.failure_type == FailureType.no_recovery
    assert report.legal_actions == []


def test_diagnosis_permission_blocked_is_terminal() -> None:
    restricted = make_retrieved_chunk(
        "restricted",
        "restricted admin key detail",
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
    )
    report = diagnose(
        _pass_result(
            reranked=[restricted],
            acl_blocked=[restricted],
            evidence_sufficient=False,
        )
    )

    assert report.failure_type == FailureType.permission_blocked
    assert report.legal_actions == [ActionType.refuse_with_explanation]


def test_diagnosis_conflict_allows_conflict_set() -> None:
    left = make_retrieved_chunk("left", "30 minutes", doc_id="doc-a", conflict_group_id="g1")
    right = make_retrieved_chunk(
        "right",
        "60 minutes",
        doc_id="doc-b",
        conflict_group_id="g1",
    )
    report = diagnose(
        _pass_result(
            reranked=[left, right],
            acl_surviving=[left, right],
            conflict_group_id="g1",
            conflicting=[left, right],
            evidence_sufficient=False,
        )
    )

    assert report.failure_type == FailureType.conflict
    assert report.conflict_group_ids == ["g1"]
    assert report.legal_actions == [
        ActionType.present_conflict_set,
        ActionType.refuse_with_explanation,
    ]


def test_diagnosis_policy_crowding_allows_filtered_retrieval() -> None:
    active = make_retrieved_chunk(
        "active",
        "current token limit",
        status=DocumentStatus.active,
    )
    deprecated = make_retrieved_chunk(
        "deprecated",
        "old token limit",
        status=DocumentStatus.deprecated,
    )
    deprecated_2 = make_retrieved_chunk(
        "deprecated-2",
        "older token limit",
        status=DocumentStatus.deprecated,
    )
    report = diagnose(
        _pass_result(
            reranked=[active, deprecated, deprecated_2],
            acl_surviving=[active],
            deprecated=[deprecated, deprecated_2],
            evidence_sufficient=False,
            top_score=0.9,
        )
    )

    assert report.failure_type == FailureType.policy_crowding
    assert report.legal_actions == [
        ActionType.filtered_retrieval,
        ActionType.refuse_with_explanation,
    ]


def test_diagnosis_policy_crowding_requires_some_clean_evidence() -> None:
    deprecated = make_retrieved_chunk(
        "deprecated",
        "old token limit",
        status=DocumentStatus.deprecated,
    )
    deprecated_2 = make_retrieved_chunk(
        "deprecated-2",
        "older token limit",
        status=DocumentStatus.deprecated,
    )
    report = diagnose(
        _pass_result(
            reranked=[deprecated, deprecated_2],
            deprecated=[deprecated, deprecated_2],
            evidence_sufficient=False,
            top_score=0.9,
        )
    )

    assert report.clean_active_count == 0
    assert report.failure_type == FailureType.no_recovery
    assert report.legal_actions == [ActionType.refuse_with_explanation]


def test_diagnosis_weak_recall_allows_rewrite() -> None:
    weak = make_retrieved_chunk("weak", "unrelated", rerank_score=0.1)
    report = diagnose(
        _pass_result(
            reranked=[weak],
            acl_surviving=[weak],
            evidence_sufficient=False,
            entity_miss=True,
            top_score=0.1,
        )
    )

    assert report.failure_type == FailureType.weak_recall
    assert report.legal_actions == [
        ActionType.rewrite_query,
        ActionType.refuse_with_explanation,
    ]


def test_diagnosis_policy_and_weak_recall_coexistence_allows_a_b_e() -> None:
    active = make_retrieved_chunk(
        "active",
        "current token limit",
        status=DocumentStatus.active,
        rerank_score=0.1,
    )
    deprecated = make_retrieved_chunk(
        "deprecated",
        "old token limit",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )
    deprecated_2 = make_retrieved_chunk(
        "deprecated-2",
        "older token limit",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )
    report = diagnose(
        _pass_result(
            reranked=[active, deprecated, deprecated_2],
            acl_surviving=[active],
            deprecated=[deprecated, deprecated_2],
            evidence_sufficient=False,
            entity_miss=True,
            top_score=0.1,
        )
    )

    assert report.failure_type == FailureType.policy_and_weak_recall
    assert report.legal_actions == [
        ActionType.rewrite_query,
        ActionType.filtered_retrieval,
        ActionType.refuse_with_explanation,
    ]


def test_diagnosis_no_recovery_defaults_to_refuse() -> None:
    neutral = make_retrieved_chunk("neutral", "some adjacent evidence")
    report = diagnose(
        _pass_result(
            reranked=[neutral],
            acl_surviving=[neutral],
            evidence_sufficient=False,
            entity_miss=False,
            top_score=0.9,
        )
    )

    assert report.failure_type == FailureType.no_recovery
    assert report.legal_actions == [ActionType.refuse_with_explanation]


def _pass_result(
    *,
    reranked,
    acl_surviving=None,
    acl_blocked=None,
    deprecated=None,
    evidence_sufficient: bool,
    entity_miss: bool = False,
    support_count: int = 0,
    top_score: float | None = None,
    conflict_group_id: str | None = None,
    conflicting=None,
) -> RetrievalPassResult:
    if top_score is not None:
        reranked = [item.model_copy(update={"rerank_score": top_score}) for item in reranked]
    return RetrievalPassResult(
        query="What is the token limit?",
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
        conflict_decision=ConflictDecision(
            has_conflict=bool(conflict_group_id),
            conflict_group_id=conflict_group_id,
            conflicting_chunks=conflicting or [],
        ),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=evidence_sufficient,
            reason="sufficient" if evidence_sufficient else "test",
            top_score=top_score,
            support_count=support_count,
            entity_miss=entity_miss,
        ),
    )
