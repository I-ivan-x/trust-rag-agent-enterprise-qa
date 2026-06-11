from __future__ import annotations

import re

from app.guards.acl_gate import apply_acl_gate
from app.guards.conflict_detector import ConflictDecision, detect_minimal_conflict
from app.guards.document_state_gate import apply_document_state_gate
from app.guards.evidence_gate import apply_evidence_gate
from app.schemas.retrieval import RetrievalOptions
from app.workflow.state import RetrievalPassResult

_QUERY_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_DEPRECATED_QUERY_TERMS = {"deprecated", "legacy", "old", "stale", "v1"}


def run_trust_gated_pass(
    *,
    query: str,
    retrieval_options: RetrievalOptions,
    retriever,
    reranker,
    user_role: str,
    user_department: str | None,
    user_clearance: str | None,
) -> RetrievalPassResult:
    warnings: list[str] = []
    retrieved_chunks = retriever.retrieve(query, retrieval_options)
    warnings.extend(getattr(retriever, "last_warnings", []))
    reranked_chunks = reranker.rerank(
        query,
        retrieved_chunks,
        top_n=retrieval_options.top_n_rerank,
    )
    state_decision = apply_document_state_gate(reranked_chunks)
    acl_decision = apply_acl_gate(
        state_decision.surviving_chunks,
        user_role=user_role,
        user_department=user_department,
        user_clearance=user_clearance,
    )
    evidence_decision = apply_evidence_gate(query, acl_decision.surviving_chunks)
    conflict_decision = (
        ConflictDecision()
        if evidence_decision.entity_miss or _query_targets_deprecated(query, state_decision)
        else detect_minimal_conflict(acl_decision.surviving_chunks)
    )
    warnings.extend(state_decision.warnings)
    warnings.extend(acl_decision.warnings)
    warnings.extend(conflict_decision.warnings)
    warnings.extend(evidence_decision.warnings)

    return RetrievalPassResult(
        query=query,
        retrieved_chunks=retrieved_chunks,
        reranked_chunks=reranked_chunks,
        state_decision=state_decision,
        acl_decision=acl_decision,
        conflict_decision=conflict_decision,
        evidence_decision=evidence_decision,
        warnings=warnings,
    )


def _query_targets_deprecated(query: str, state_decision) -> bool:
    if not state_decision.deprecated_chunks:
        return False
    query_terms = set(_QUERY_TOKEN_PATTERN.findall(query.lower()))
    return bool(query_terms & _DEPRECATED_QUERY_TERMS)
