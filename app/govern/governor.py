from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.govern.conditions import (
    RISK_TIER,
    ActorContext,
    ConditionReport,
    GovernanceAction,
)
from app.govern.controller import GovernanceControllerContext
from app.govern.executor import execute_governance_action
from app.govern.sinks import ActionRecord, ActionSink
from app.govern.validator import (
    GovernanceBudget,
    GovernanceProposal,
    GovValidationResult,
    validate_governance,
)
from app.workflow.state import RetrievalPassResult


@dataclass
class GovernanceOutcome:
    proposal: GovernanceProposal
    validation: GovValidationResult
    record: ActionRecord | None
    trace: dict[str, Any]


def govern(
    report: ConditionReport,
    pass_result: RetrievalPassResult,
    actor: ActorContext,
    controller,
    sink: ActionSink,
    *,
    budget: GovernanceBudget | None = None,
) -> GovernanceOutcome:
    if not report.conditions:
        proposal = GovernanceProposal(
            action=GovernanceAction.no_op,
            source="rule",
            controller_source=getattr(controller, "controller_source", "rule"),
        )
        return GovernanceOutcome(
            proposal=proposal,
            validation=GovValidationResult(ok=True),
            record=None,
            trace=_trace(
                report=report,
                proposal=proposal,
                validation=GovValidationResult(ok=True),
                record=None,
                forced=False,
                validator_verdict="no_op",
            ),
        )

    context = GovernanceControllerContext.from_pass_result(pass_result)
    proposal = controller.select(report, context)
    validation = validate_governance(
        proposal,
        report,
        budget or GovernanceBudget(),
    )
    forced = False
    executable = proposal
    if not validation.ok:
        forced = True
        executable = proposal.model_copy(
            update={
                "action": validation.forced_action,
                "source": proposal.source,
                "args": {
                    "reason": validation.reject_reason,
                    "evidence_citations": proposal.args.get("evidence_citations", []),
                },
            }
        )

    record = execute_governance_action(
        executable.action,
        report,
        pass_result,
        actor,
        sink,
        evidence_citations=executable.args.get("evidence_citations"),
    )
    return GovernanceOutcome(
        proposal=executable,
        validation=validation,
        record=record,
        trace=_trace(
            report=report,
            proposal=proposal,
            validation=validation,
            record=record,
            forced=forced,
            validator_verdict="accepted" if validation.ok else "rejected",
        ),
    )


def _trace(
    *,
    report: ConditionReport,
    proposal: GovernanceProposal,
    validation: GovValidationResult,
    record: ActionRecord | None,
    forced: bool,
    validator_verdict: str,
) -> dict[str, Any]:
    action = validation.forced_action if forced else proposal.action
    risk_tier = RISK_TIER.get(action) if action is not None else None
    return {
        "conditions": [condition.value for condition in report.conditions],
        "proposed_action": proposal.action.value,
        "controller_source": proposal.controller_source,
        "risk_tier": risk_tier.value if risk_tier is not None else None,
        "validator_verdict": validator_verdict,
        "validator_reject_reason": validation.reject_reason,
        "forced": forced,
        "approval_state": record.approval_state if record is not None else None,
        "sink_record_id": record.record_id if record is not None else None,
    }
