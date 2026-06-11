from __future__ import annotations

from app.answer.refusal_controller import decide_response_mode
from app.core.enums import ExpectedBehavior
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from tests.helpers import make_retrieved_chunk


def test_permission_priority_is_highest() -> None:
    blocked = make_retrieved_chunk("chunk-blocked", "Restricted.")

    decision = decide_response_mode(
        acl_decision=ACLGateDecision(blocked_chunks=[blocked]),
        conflict_decision=ConflictDecision(
            has_conflict=True,
            conflict_group_id="g1",
            conflicting_chunks=[make_retrieved_chunk("chunk-conflict", "Conflict.")],
        ),
        evidence_decision=_sufficient_evidence(),
    )

    assert decision.response_mode == ExpectedBehavior.refuse_permission


def test_conflict_before_deprecated() -> None:
    conflict_chunk = make_retrieved_chunk("chunk-conflict", "Conflict.")
    deprecated = make_retrieved_chunk("chunk-deprecated", "Deprecated.")

    decision = decide_response_mode(
        state_decision=StateGateDecision(deprecated_chunks=[deprecated]),
        acl_decision=ACLGateDecision(surviving_chunks=[conflict_chunk]),
        conflict_decision=ConflictDecision(
            has_conflict=True,
            conflict_group_id="g1",
            conflicting_chunks=[conflict_chunk],
        ),
        evidence_decision=_sufficient_evidence(),
        deprecated_warning=True,
    )

    assert decision.response_mode == ExpectedBehavior.report_conflict


def test_deprecated_before_answer() -> None:
    deprecated = make_retrieved_chunk("chunk-deprecated", "Deprecated.")

    decision = decide_response_mode(
        state_decision=StateGateDecision(deprecated_chunks=[deprecated]),
        acl_decision=ACLGateDecision(surviving_chunks=[make_retrieved_chunk("chunk-a", "A.")]),
        conflict_decision=ConflictDecision(),
        evidence_decision=_sufficient_evidence(),
        deprecated_warning=True,
    )

    assert decision.response_mode == ExpectedBehavior.warn_deprecated


def test_no_evidence_refusal() -> None:
    decision = decide_response_mode(
        acl_decision=ACLGateDecision(surviving_chunks=[]),
        conflict_decision=ConflictDecision(),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=False,
            reason="no_surviving_chunks",
            support_count=0,
        ),
    )

    assert decision.response_mode == ExpectedBehavior.refuse_no_evidence


def test_answer_mode_when_sufficient() -> None:
    chunk = make_retrieved_chunk("chunk-a", "A.")

    decision = decide_response_mode(
        acl_decision=ACLGateDecision(surviving_chunks=[chunk]),
        conflict_decision=ConflictDecision(),
        evidence_decision=_sufficient_evidence(),
    )

    assert decision.response_mode == ExpectedBehavior.answer
    assert decision.should_answer is True


def test_system_error_fallback() -> None:
    decision = decide_response_mode(system_error=True)

    assert decision.response_mode == ExpectedBehavior.system_error
    assert decision.should_answer is False


def test_response_mode_is_one_of_allowed_six_and_no_ask_clarification() -> None:
    allowed = {
        ExpectedBehavior.answer,
        ExpectedBehavior.refuse_no_evidence,
        ExpectedBehavior.refuse_permission,
        ExpectedBehavior.warn_deprecated,
        ExpectedBehavior.report_conflict,
        ExpectedBehavior.system_error,
    }

    decision = decide_response_mode(system_error=True)

    assert decision.response_mode in allowed
    assert decision.response_mode != "ask_clarification"


def _sufficient_evidence() -> EvidenceGateDecision:
    return EvidenceGateDecision(
        evidence_sufficient=True,
        reason="sufficient",
        top_score=0.8,
        support_count=1,
    )
