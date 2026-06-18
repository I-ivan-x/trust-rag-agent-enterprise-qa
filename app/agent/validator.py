from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.agent.actions import ActionProposal
from app.agent.diagnosis import ActionType, DiagnosisReport, FailureType

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
_FILTER_WHITELIST = {"status", "exclude_doc_ids"}
_NONTERMINAL_ACTIONS = {
    ActionType.rewrite_query,
    ActionType.filtered_retrieval,
}


class ActionBudget(BaseModel):
    max_nonterminal_actions: int = Field(default=2, ge=0)
    consumed_nonterminal_actions: int = Field(default=0, ge=0)
    used_action_types: list[ActionType] = Field(default_factory=list)

    @property
    def remaining(self) -> int:
        return self.max_nonterminal_actions - self.consumed_nonterminal_actions

    def consume(self, action: ActionType) -> ActionBudget:
        consumed = self.consumed_nonterminal_actions
        used = list(self.used_action_types)
        if action in _NONTERMINAL_ACTIONS:
            consumed += 1
            used.append(action)
        return self.model_copy(
            update={
                "consumed_nonterminal_actions": consumed,
                "used_action_types": used,
            }
        )


class ValidationResult(BaseModel):
    ok: bool
    reject_reason: str | None = None


def validate(
    proposal: ActionProposal,
    diagnosis: DiagnosisReport,
    budget: ActionBudget,
) -> ValidationResult:
    if proposal.action not in diagnosis.legal_actions:
        return _reject("action_not_legal_for_diagnosis")
    if (
        diagnosis.failure_type == FailureType.permission_blocked
        and proposal.action != ActionType.refuse_with_explanation
    ):
        return _reject("permission_blocked_requires_refusal")
    if proposal.action in _NONTERMINAL_ACTIONS:
        if budget.remaining <= 0:
            return _reject("budget_exhausted")
        if proposal.action in budget.used_action_types:
            return _reject("duplicate_action_type")
    if proposal.action == ActionType.filtered_retrieval:
        filter_result = _validate_filters(proposal.args.get("filters") or {})
        if not filter_result.ok:
            return filter_result
    if proposal.action == ActionType.rewrite_query:
        rewrite_result = _validate_rewrite_entities(proposal)
        if not rewrite_result.ok:
            return rewrite_result
    return ValidationResult(ok=True)


def _validate_filters(filters: dict) -> ValidationResult:
    unknown = set(filters) - _FILTER_WHITELIST
    if unknown:
        return _reject(f"filter_field_not_allowed:{','.join(sorted(unknown))}")
    status = filters.get("status")
    if status is not None:
        if isinstance(status, list):
            allowed_status = set(status) == {"active"}
        else:
            allowed_status = str(status) == "active"
        if not allowed_status:
            return _reject("status_filter_must_only_allow_active")
    exclude_doc_ids = filters.get("exclude_doc_ids")
    if exclude_doc_ids is not None and not isinstance(exclude_doc_ids, list):
        return _reject("exclude_doc_ids_must_be_list")
    return ValidationResult(ok=True)


def _validate_rewrite_entities(proposal: ActionProposal) -> ValidationResult:
    rewritten = str(proposal.args.get("rewritten_query") or "")
    if not rewritten:
        return _reject("rewritten_query_missing")
    allowed = set(proposal.args.get("_allowed_entity_terms") or [])
    if not allowed:
        return _reject("rewrite_allowed_entities_missing")
    extra = _entity_terms(rewritten) - allowed
    if extra:
        return _reject(f"rewrite_entities_not_allowed:{','.join(sorted(extra))}")
    return ValidationResult(ok=True)


def _entity_terms(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if token not in _STOPWORDS and (len(token) >= 3 or token in {"v1", "v2"})
    }


def _reject(reason: str) -> ValidationResult:
    return ValidationResult(ok=False, reject_reason=reason)
