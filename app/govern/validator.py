from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.govern.conditions import (
    RISK_TIER,
    ConditionReport,
    GovernanceAction,
    OpsCondition,
    RiskTier,
)

LEGAL_ACTIONS: dict[OpsCondition, list[GovernanceAction]] = {
    OpsCondition.stale_procedure: [
        GovernanceAction.flag_stale,
        GovernanceAction.escalate_to_human,
    ],
    OpsCondition.config_violation: [
        GovernanceAction.open_remediation_ticket,
        GovernanceAction.escalate_to_human,
    ],
    OpsCondition.policy_violation: [
        GovernanceAction.open_remediation_ticket,
        GovernanceAction.escalate_to_human,
    ],
    OpsCondition.missing_prereq: [
        GovernanceAction.open_remediation_ticket,
        GovernanceAction.escalate_to_human,
    ],
    OpsCondition.broken_xref: [
        GovernanceAction.open_remediation_ticket,
        GovernanceAction.escalate_to_human,
    ],
    OpsCondition.active_active_conflict: [
        GovernanceAction.send_alert,
        GovernanceAction.escalate_to_human,
    ],
    OpsCondition.permission_blocked: [GovernanceAction.escalate_to_human],
    OpsCondition.insufficient_evidence: [GovernanceAction.escalate_to_human],
}


class GovernanceProposal(BaseModel):
    action: GovernanceAction
    args: dict[str, Any] = Field(default_factory=dict)
    source: str = "rule"
    reason: str | None = None
    controller_source: str | None = None
    llm_raw_proposal: dict[str, Any] | None = None
    accepted: bool = True
    fallback_reason: str | None = None


class GovernanceBudget(BaseModel):
    max_actions: int = Field(default=3, ge=0, le=3)
    consumed: int = Field(default=0, ge=0)

    @property
    def remaining(self) -> int:
        return self.max_actions - self.consumed

    def consume(self) -> GovernanceBudget:
        return self.model_copy(update={"consumed": self.consumed + 1})


class GovValidationResult(BaseModel):
    ok: bool
    reject_reason: str | None = None
    forced_action: GovernanceAction | None = None


def validate_governance(
    proposal: GovernanceProposal,
    report: ConditionReport,
    budget: GovernanceBudget,
) -> GovValidationResult:
    if proposal.action == GovernanceAction.no_op:
        return _reject("no_op_not_validated")
    if proposal.action not in RISK_TIER:
        return _reject("action_not_whitelisted")
    if budget.consumed >= budget.max_actions:
        return _reject("budget_exhausted")
    if report.conditions:
        legal_actions = _legal_actions(report)
        if proposal.action not in legal_actions:
            return _reject("action_not_legal_for_conditions")
    else:
        return _reject("no_condition_requires_no_op")

    if (
        proposal.action != GovernanceAction.escalate_to_human
        and report.evidence_decision != "sufficient"
    ):
        return _reject("insufficient_evidence_requires_escalation")

    risk_tier = RISK_TIER[proposal.action]
    if risk_tier in {RiskTier.auto, RiskTier.approval} and not report.authorized_actor:
        return _reject("unauthorized_requires_escalation")

    return GovValidationResult(ok=True)


def legal_actions_for_report(report: ConditionReport) -> list[GovernanceAction]:
    if not report.conditions:
        return [GovernanceAction.no_op]
    return sorted(_legal_actions(report), key=lambda action: action.value)


def _legal_actions(report: ConditionReport) -> set[GovernanceAction]:
    legal: set[GovernanceAction] = set()
    for condition in report.conditions:
        legal.update(LEGAL_ACTIONS.get(condition, [GovernanceAction.escalate_to_human]))
    legal.add(GovernanceAction.escalate_to_human)
    return legal


def _reject(reason: str) -> GovValidationResult:
    return GovValidationResult(
        ok=False,
        reject_reason=reason,
        forced_action=GovernanceAction.escalate_to_human,
    )
