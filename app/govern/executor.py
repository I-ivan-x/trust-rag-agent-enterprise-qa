from __future__ import annotations

from collections.abc import Sequence

from app.govern.conditions import (
    RISK_TIER,
    ActorContext,
    ConditionReport,
    GovernanceAction,
    OpsCondition,
    RiskTier,
)
from app.govern.sinks import ActionRecord, ActionSink
from app.schemas.retrieval import RetrievedChunk
from app.workflow.state import RetrievalPassResult


def execute_governance_action(
    action: GovernanceAction,
    report: ConditionReport,
    pass_result: RetrievalPassResult,
    actor: ActorContext,
    sink: ActionSink,
    *,
    evidence_citations: Sequence[str] | None = None,
) -> ActionRecord:
    if action == GovernanceAction.no_op:
        raise ValueError("no_op is not a sink action")

    citations = _validated_citations(
        pass_result,
        evidence_citations or _default_citations(pass_result),
    )
    condition = _primary_condition(report)
    doc_ids = _doc_ids_for_action(action, report, pass_result)
    risk_tier = RISK_TIER[action]

    if risk_tier == RiskTier.auto:
        return sink.record_action(
            action=action,
            condition=condition,
            doc_ids=doc_ids,
            evidence_citations=citations,
            actor_role=actor.role,
            risk_tier=risk_tier,
            approval_state="committed",
        )
    if risk_tier == RiskTier.approval:
        return sink.record_action(
            action=action,
            condition=condition,
            doc_ids=doc_ids,
            evidence_citations=citations,
            actor_role=actor.role,
            risk_tier=risk_tier,
            approval_state="pending_approval",
        )
    return sink.record_action(
        action=action,
        condition=condition,
        doc_ids=doc_ids,
        evidence_citations=citations,
        actor_role=actor.role,
        risk_tier=risk_tier,
        approval_state="escalated",
    )


def _primary_condition(report: ConditionReport) -> OpsCondition | None:
    return report.conditions[0] if report.conditions else None


def _doc_ids_for_action(
    action: GovernanceAction,
    report: ConditionReport,
    pass_result: RetrievalPassResult,
) -> list[str]:
    if action == GovernanceAction.flag_stale and report.stale_doc_ids:
        return report.stale_doc_ids
    if action == GovernanceAction.open_remediation_ticket:
        candidates = [
            *report.violating_doc_ids,
            *report.broken_xref_doc_ids,
            *report.stale_doc_ids,
        ]
        if candidates:
            return sorted(set(candidates))
    if action == GovernanceAction.send_alert:
        conflict_doc_ids = _conflict_doc_ids(pass_result)
        if conflict_doc_ids:
            return conflict_doc_ids
    return _context_doc_ids(pass_result)


def _validated_citations(
    pass_result: RetrievalPassResult,
    evidence_citations: Sequence[str],
) -> list[str]:
    context_chunk_ids = _context_chunk_ids(pass_result)
    out_of_context = sorted(set(evidence_citations) - context_chunk_ids)
    if out_of_context:
        raise ValueError(f"evidence citations are not in context: {out_of_context}")
    return list(dict.fromkeys(evidence_citations))


def _default_citations(pass_result: RetrievalPassResult) -> list[str]:
    candidates = pass_result.acl_decision.surviving_chunks or pass_result.reranked_chunks
    return [result.chunk.chunk_id for result in candidates[:5]]


def _context_chunk_ids(pass_result: RetrievalPassResult) -> set[str]:
    return {result.chunk.chunk_id for result in _context_chunks(pass_result)}


def _context_doc_ids(pass_result: RetrievalPassResult) -> list[str]:
    return sorted({result.chunk.doc_id for result in _context_chunks(pass_result)})


def _context_chunks(pass_result: RetrievalPassResult) -> list[RetrievedChunk]:
    by_chunk_id: dict[str, RetrievedChunk] = {}
    for result in [
        *pass_result.reranked_chunks,
        *pass_result.acl_decision.surviving_chunks,
        *pass_result.state_decision.deprecated_chunks,
        *pass_result.conflict_decision.conflicting_chunks,
    ]:
        by_chunk_id[result.chunk.chunk_id] = result
    return list(by_chunk_id.values())


def _conflict_doc_ids(pass_result: RetrievalPassResult) -> list[str]:
    return sorted(
        {result.chunk.doc_id for result in pass_result.conflict_decision.conflicting_chunks}
    )
