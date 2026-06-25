"""Q4-P4 dev-hardening tests (SPEC_Q4_P4_P5 §1.1 R2, §1.2 R1).

R2: govern-local INSUFFICIENT signal -- when there is no query-relevant ops evidence
    (top rerank score below GOVERN_RELEVANCE_FLOOR) and no other condition, escalate.
R1: a stale_procedure SOP only triggers STALE_PROCEDURE when it is query-relevant, so an
    incidental low-score stale SOP cannot hijack an xref/config case into flag_stale.

Both are governance-local: they read rerank scores already on the pass result and never
touch the shared Q1/Q2 evidence gate.
"""

from __future__ import annotations

from app.core.enums import DocumentStatus
from app.govern.conditions import (
    ActorContext,
    GovernanceAction,
    OpsCondition,
    detect_conditions,
)
from app.govern.context import GovernanceControllerContext
from app.govern.controller import GovernanceRuleController
from app.govern.governor import govern
from app.govern.sinks import LocalJsonlSink
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.schemas.retrieval import RetrievedChunk
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


# --------------------------------------------------------------------------- #
# R2: govern-local INSUFFICIENT
# --------------------------------------------------------------------------- #
def test_govern_local_insufficient_escalates(tmp_path) -> None:
    # Topically-adjacent chunk survives the shared gate (evidence_sufficient=True) but is
    # not query-relevant (low rerank score). Governance must escalate, not no_op.
    weak = make_retrieved_chunk("weak", "loosely related security note", rerank_score=0.02)
    report = detect_conditions(
        _pass_result(reranked=[weak], acl_surviving=[weak], evidence_sufficient=True),
        ActorContext(role="admin"),
    )
    assert report.conditions == [OpsCondition.insufficient_evidence]
    assert report.evidence_decision == "insufficient"

    outcome = govern(
        report,
        _pass_result(reranked=[weak], acl_surviving=[weak], evidence_sufficient=True),
        ActorContext(role="admin"),
        GovernanceRuleController(),
        LocalJsonlSink(tmp_path),
    )
    assert outcome.proposal.action == GovernanceAction.escalate_to_human


def test_no_local_insufficient_when_relevant() -> None:
    strong = make_retrieved_chunk("strong", "directly answers the query", rerank_score=0.95)
    report = detect_conditions(
        _pass_result(reranked=[strong], acl_surviving=[strong], evidence_sufficient=True),
        ActorContext(role="admin"),
    )
    assert report.conditions == []
    assert report.evidence_decision == "sufficient"
    proposal = GovernanceRuleController().select(report, GovernanceControllerContext())
    assert proposal.action == GovernanceAction.no_op


def test_local_insufficient_noop_without_rerank_scores() -> None:
    # No rerank scores (identity-reranker fallback) -> R2 is a no-op; shared gate stands.
    chunk = make_retrieved_chunk("c", "some content", rerank_score=None)
    report = detect_conditions(
        _pass_result(reranked=[chunk], acl_surviving=[chunk], evidence_sufficient=True),
        ActorContext(role="admin"),
    )
    assert report.conditions == []


# --------------------------------------------------------------------------- #
# R1: stale relevance
# --------------------------------------------------------------------------- #
def test_stale_suppressed_when_irrelevant_xref_wins() -> None:
    # Incidental low-score stale SOP must not hijack an xref case into flag_stale.
    xref = _with_signals(
        make_retrieved_chunk(
            "xref", "Step 2 references missing rollback doc", doc_id="doc-upgrade",
            rerank_score=0.95,
        ),
        overlay_relation_note={
            "type": "xref",
            "target_doc_id": "doc-rollback",
            "target_status": "missing",
        },
    )
    incidental_stale = _with_signals(
        make_retrieved_chunk(
            "stale", "unrelated deprecation checklist", doc_id="sop-deprecation-checks",
            rerank_score=0.04, rank=2,
        ),
        overlay_relation_note={"type": "stale_procedure", "anchor_docs": ["x"]},
    )
    report = detect_conditions(
        _pass_result(
            reranked=[xref, incidental_stale],
            acl_surviving=[xref, incidental_stale],
        ),
        ActorContext(role="editor"),
    )
    assert OpsCondition.stale_procedure not in report.conditions
    assert OpsCondition.broken_xref in report.conditions
    proposal = GovernanceRuleController().select(
        report,
        GovernanceControllerContext(doc_ids=["doc-upgrade"]),
    )
    assert proposal.action == GovernanceAction.open_remediation_ticket


def test_stale_fires_when_relevant() -> None:
    sop = _with_signals(
        make_retrieved_chunk(
            "sop", "runbook still reads deprecated API directly", doc_id="sop-deprecation-checks",
            rerank_score=0.97,
        ),
        overlay_relation_note={"type": "stale_procedure", "anchor_docs": ["x"]},
    )
    report = detect_conditions(
        _pass_result(reranked=[sop], acl_surviving=[sop]),
        ActorContext(role="editor"),
    )
    assert OpsCondition.stale_procedure in report.conditions


def test_stale_relevance_noop_without_scores() -> None:
    sop = _with_signals(
        make_retrieved_chunk(
            "sop", "stale procedure sop", doc_id="sop-deprecation-checks", rerank_score=None
        ),
        overlay_relation_note={"type": "stale_procedure", "anchor_docs": ["x"]},
    )
    report = detect_conditions(
        _pass_result(reranked=[sop], acl_surviving=[sop]),
        ActorContext(role="editor"),
    )
    assert OpsCondition.stale_procedure in report.conditions


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _pass_result(
    *,
    reranked: list[RetrievedChunk] | None = None,
    acl_surviving: list[RetrievedChunk] | None = None,
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
        ),
        acl_decision=ACLGateDecision(surviving_chunks=acl_surviving or []),
        conflict_decision=ConflictDecision(),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=evidence_sufficient,
            reason="sufficient" if evidence_sufficient else "test_insufficient",
            support_count=len(acl_surviving or reranked),
            entity_miss=not evidence_sufficient,
        ),
    )


def _with_signals(result: RetrievedChunk, **signals) -> RetrievedChunk:
    return result.model_copy(update={"chunk": result.chunk.model_copy(update=signals)})
