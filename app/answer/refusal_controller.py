from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import ExpectedBehavior
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.schemas.retrieval import RetrievedChunk


class RefusalDecision(BaseModel):
    response_mode: ExpectedBehavior
    should_answer: bool
    reason: str
    selected_chunks: list[RetrievedChunk] = Field(default_factory=list)
    citations_required: bool = False
    warnings: list[str] = Field(default_factory=list)


def decide_response_mode(
    *,
    state_decision: StateGateDecision | None = None,
    acl_decision: ACLGateDecision | None = None,
    conflict_decision: ConflictDecision | None = None,
    evidence_decision: EvidenceGateDecision | None = None,
    permission_denied: bool | None = None,
    deprecated_warning: bool = False,
    system_error: bool = False,
    warnings: list[str] | None = None,
) -> RefusalDecision:
    collected_warnings = list(warnings or [])
    if system_error:
        return RefusalDecision(
            response_mode=ExpectedBehavior.system_error,
            should_answer=False,
            reason="system_error",
            selected_chunks=[],
            warnings=collected_warnings,
        )

    permission_blocked = (
        permission_denied
        if permission_denied is not None
        else bool(
            acl_decision
            and acl_decision.blocked_chunks
            and not acl_decision.surviving_chunks
        )
    )
    if permission_blocked:
        return RefusalDecision(
            response_mode=ExpectedBehavior.refuse_permission,
            should_answer=False,
            reason="permission_denied",
            selected_chunks=[],
            warnings=[*collected_warnings, *acl_decision.warnings],
        )

    if conflict_decision and conflict_decision.has_conflict:
        return RefusalDecision(
            response_mode=ExpectedBehavior.report_conflict,
            should_answer=False,
            reason="conflict_detected",
            selected_chunks=conflict_decision.conflicting_chunks,
            citations_required=True,
            warnings=[*collected_warnings, *conflict_decision.warnings],
        )

    if deprecated_warning and state_decision and state_decision.deprecated_chunks:
        return RefusalDecision(
            response_mode=ExpectedBehavior.warn_deprecated,
            should_answer=False,
            reason="deprecated_only",
            selected_chunks=state_decision.deprecated_chunks,
            citations_required=True,
            warnings=[*collected_warnings, *state_decision.warnings],
        )

    if evidence_decision and not evidence_decision.evidence_sufficient:
        return RefusalDecision(
            response_mode=ExpectedBehavior.refuse_no_evidence,
            should_answer=False,
            reason="no_evidence",
            selected_chunks=[],
            warnings=[*collected_warnings, *evidence_decision.warnings],
        )

    selected_chunks = acl_decision.surviving_chunks if acl_decision else []
    return RefusalDecision(
        response_mode=ExpectedBehavior.answer,
        should_answer=True,
        reason="none",
        selected_chunks=selected_chunks,
        citations_required=True,
        warnings=collected_warnings,
    )
