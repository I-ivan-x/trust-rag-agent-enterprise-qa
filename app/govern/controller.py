from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.govern.conditions import ConditionReport, GovernanceAction, OpsCondition
from app.govern.validator import GovernanceProposal
from app.workflow.state import RetrievalPassResult


class GovernanceControllerContext(BaseModel):
    query: str = ""
    neighborhood: list[dict[str, Any]] = Field(default_factory=list)
    evidence_citations: list[str] = Field(default_factory=list)
    doc_ids: list[str] = Field(default_factory=list)
    conflict_doc_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_pass_result(cls, pass_result: RetrievalPassResult) -> GovernanceControllerContext:
        neighborhood: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        for result in [
            *pass_result.acl_decision.surviving_chunks,
            *pass_result.reranked_chunks,
            *pass_result.state_decision.deprecated_chunks,
            *pass_result.conflict_decision.conflicting_chunks,
        ]:
            chunk = result.chunk
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            neighborhood.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "status": chunk.status.value,
                    "section_path": chunk.section_path,
                }
            )
        return cls(
            query=pass_result.query,
            neighborhood=neighborhood,
            evidence_citations=[item["chunk_id"] for item in neighborhood[:5]],
            doc_ids=sorted({item["doc_id"] for item in neighborhood}),
            conflict_doc_ids=sorted(
                {result.chunk.doc_id for result in pass_result.conflict_decision.conflicting_chunks}
            ),
        )


class GovernanceRuleController:
    controller_source = "rule"

    def select(
        self,
        report: ConditionReport,
        context: GovernanceControllerContext | None = None,
    ) -> GovernanceProposal:
        context = context or GovernanceControllerContext()
        if not report.conditions:
            return _proposal(GovernanceAction.no_op, context=context)
        if OpsCondition.permission_blocked in report.conditions or not report.authorized_actor:
            return _escalate("permission_blocked", context)
        if OpsCondition.insufficient_evidence in report.conditions:
            return _escalate("insufficient_evidence", context)
        if OpsCondition.active_active_conflict in report.conditions:
            return _proposal(
                GovernanceAction.send_alert,
                context=context,
                args={
                    "doc_ids": context.conflict_doc_ids or context.doc_ids,
                    "evidence_citations": context.evidence_citations,
                    "conflict_group_ids": report.conflict_group_ids,
                },
            )
        if any(
            condition in report.conditions
            for condition in (
                OpsCondition.config_violation,
                OpsCondition.policy_violation,
                OpsCondition.missing_prereq,
                OpsCondition.broken_xref,
            )
        ):
            doc_ids = sorted(
                {
                    *report.violating_doc_ids,
                    *report.broken_xref_doc_ids,
                    *context.doc_ids,
                }
            )
            return _proposal(
                GovernanceAction.open_remediation_ticket,
                context=context,
                args={
                    "doc_ids": doc_ids,
                    "evidence_citations": context.evidence_citations,
                },
            )
        if OpsCondition.stale_procedure in report.conditions:
            return _proposal(
                GovernanceAction.flag_stale,
                context=context,
                args={
                    "doc_ids": report.stale_doc_ids,
                    "stale_doc_ids": report.stale_doc_ids,
                    "evidence_citations": context.evidence_citations,
                },
            )
        return _escalate("no_valid_action", context)


def _proposal(
    action: GovernanceAction,
    *,
    context: GovernanceControllerContext,
    args: dict[str, Any] | None = None,
) -> GovernanceProposal:
    del context
    return GovernanceProposal(
        action=action,
        args=args or {},
        source="rule",
        controller_source="rule",
    )


def _escalate(reason: str, context: GovernanceControllerContext) -> GovernanceProposal:
    return _proposal(
        GovernanceAction.escalate_to_human,
        context=context,
        args={"reason": reason, "evidence_citations": context.evidence_citations},
    )
