from __future__ import annotations

from app.answer.refusal_controller import decide_response_mode
from app.core.enums import DocumentStatus, ExpectedBehavior
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision, detect_minimal_conflict
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from tests.helpers import make_retrieved_chunk


def test_active_active_same_conflict_group_triggers() -> None:
    first = make_retrieved_chunk("chunk-a", "30 minutes.", doc_id="doc-a", conflict_group_id="g1")
    second = make_retrieved_chunk("chunk-b", "60 minutes.", doc_id="doc-b", conflict_group_id="g1")

    decision = detect_minimal_conflict([first, second])

    assert decision.has_conflict is True
    assert decision.conflict_group_id == "g1"
    assert {chunk.chunk.doc_id for chunk in decision.conflicting_chunks} == {"doc-a", "doc-b"}


def test_active_deprecated_same_conflict_group_does_not_trigger() -> None:
    first = make_retrieved_chunk("chunk-a", "30 minutes.", doc_id="doc-a", conflict_group_id="g1")
    second = make_retrieved_chunk(
        "chunk-b",
        "60 minutes.",
        doc_id="doc-b",
        conflict_group_id="g1",
        status=DocumentStatus.deprecated,
    )

    decision = detect_minimal_conflict([first, second])

    assert decision.has_conflict is False


def test_different_conflict_group_does_not_trigger() -> None:
    first = make_retrieved_chunk("chunk-a", "30 minutes.", doc_id="doc-a", conflict_group_id="g1")
    second = make_retrieved_chunk("chunk-b", "60 minutes.", doc_id="doc-b", conflict_group_id="g2")

    assert detect_minimal_conflict([first, second]).has_conflict is False


def test_same_doc_multiple_chunks_does_not_trigger() -> None:
    first = make_retrieved_chunk("chunk-a", "30 minutes.", doc_id="doc-a", conflict_group_id="g1")
    second = make_retrieved_chunk("chunk-b", "More detail.", doc_id="doc-a", conflict_group_id="g1")

    assert detect_minimal_conflict([first, second]).has_conflict is False


def test_permission_priority_beats_conflict() -> None:
    blocked = make_retrieved_chunk("chunk-blocked", "Restricted.")
    conflict = ConflictDecision(
        has_conflict=True,
        conflict_group_id="g1",
        conflicting_chunks=[make_retrieved_chunk("chunk-a", "A.")],
    )

    decision = decide_response_mode(
        state_decision=StateGateDecision(),
        acl_decision=ACLGateDecision(surviving_chunks=[], blocked_chunks=[blocked]),
        conflict_decision=conflict,
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=True,
            reason="sufficient",
            support_count=1,
        ),
    )

    assert decision.response_mode == ExpectedBehavior.refuse_permission
