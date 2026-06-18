from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.agent.diagnosis import ActionType
from app.core.enums import DocumentStatus
from app.guards.evidence_gate import EvidenceGateConfig
from app.retrieval.query_rewriter import rewrite_query_for_evidence
from app.schemas.retrieval import RetrievalOptions
from app.workflow.orchestrator import run_trust_gated_pass
from app.workflow.state import RetrievalPassResult

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "do",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "which",
    "with",
}


class ActionProposal(BaseModel):
    action: ActionType
    args: dict[str, Any] = Field(default_factory=dict)
    source: str = "rule"


@dataclass
class ActionResult:
    action: ActionType
    query: str
    pass_result: RetrievalPassResult | None = None
    terminal_reason: str | None = None
    warnings: list[str] = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


def materialize_proposal(
    proposal: ActionProposal,
    *,
    query: str,
    pass_result: RetrievalPassResult,
) -> ActionProposal:
    if proposal.action == ActionType.rewrite_query:
        args = dict(proposal.args)
        if not args.get("rewritten_query"):
            decision = rewrite_query_for_evidence(query)
            args["rewritten_query"] = decision.rewritten_query or query
            args["rewrite_reason"] = decision.reason
        args["_allowed_entity_terms"] = sorted(
            _entity_terms(query) | _retrieval_summary_terms(pass_result)
        )
        return proposal.model_copy(update={"args": args})

    if proposal.action == ActionType.filtered_retrieval:
        args = dict(proposal.args)
        args.setdefault("filters", _tightening_filters(pass_result))
        return proposal.model_copy(update={"args": args})

    if proposal.action == ActionType.present_conflict_set:
        args = dict(proposal.args)
        if not args.get("conflict_doc_ids"):
            args["conflict_doc_ids"] = _conflict_doc_ids(pass_result)
        return proposal.model_copy(update={"args": args})

    if proposal.action == ActionType.refuse_with_explanation:
        args = dict(proposal.args)
        args.setdefault("reason", "no_legal_recovery_action")
        return proposal.model_copy(update={"args": args})

    return proposal


def execute_action(
    proposal: ActionProposal,
    query: str,
    retriever,
    reranker,
    settings,
    *,
    retrieval_options: RetrievalOptions | None = None,
    evidence_gate_config: EvidenceGateConfig | None = None,
    user_role: str = "employee",
    user_department: str | None = None,
    user_clearance: str | None = "internal",
) -> ActionResult:
    del settings
    if proposal.action == ActionType.refuse_with_explanation:
        return ActionResult(
            action=proposal.action,
            query=query,
            terminal_reason="refuse",
            warnings=[str(proposal.args.get("reason") or "refuse")],
        )
    if proposal.action == ActionType.present_conflict_set:
        return ActionResult(
            action=proposal.action,
            query=query,
            terminal_reason="conflict_set",
        )

    if proposal.action == ActionType.rewrite_query:
        next_query = str(proposal.args.get("rewritten_query") or query)
        filters = None
    elif proposal.action == ActionType.filtered_retrieval:
        next_query = query
        filters = proposal.args.get("filters") or {}
    else:
        return ActionResult(
            action=proposal.action,
            query=query,
            terminal_reason="refuse",
            warnings=[f"unsupported_action:{proposal.action.value}"],
        )

    pass_result = run_trust_gated_pass(
        query=next_query,
        retrieval_options=retrieval_options or RetrievalOptions(return_trace=True),
        retriever=retriever,
        reranker=reranker,
        user_role=user_role,
        user_department=user_department,
        user_clearance=user_clearance,
        evidence_gate_config=evidence_gate_config,
        filters=filters,
    )
    return ActionResult(
        action=proposal.action,
        query=next_query,
        pass_result=pass_result,
    )


def _tightening_filters(pass_result: RetrievalPassResult) -> dict[str, Any]:
    excluded = {
        result.chunk.doc_id
        for result in [
            *pass_result.state_decision.deprecated_chunks,
            *pass_result.state_decision.blocked_chunks,
            *pass_result.acl_decision.blocked_chunks,
        ]
    }
    return {
        "status": DocumentStatus.active.value,
        "exclude_doc_ids": sorted(excluded),
    }


def _conflict_doc_ids(pass_result: RetrievalPassResult) -> list[str]:
    return sorted(
        {result.chunk.doc_id for result in pass_result.conflict_decision.conflicting_chunks}
    )


def _retrieval_summary_terms(pass_result: RetrievalPassResult) -> set[str]:
    terms: set[str] = set()
    for result in pass_result.reranked_chunks[:5]:
        terms.update(_entity_terms(" ".join([*result.chunk.section_path, result.chunk.text])))
    return terms


def _entity_terms(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if token not in _STOPWORDS and (len(token) >= 3 or token in {"v1", "v2"})
    }
