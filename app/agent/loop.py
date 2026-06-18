from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.actions import ActionProposal, execute_action, materialize_proposal
from app.agent.controller import RuleController
from app.agent.diagnosis import ActionType, DiagnosisReport, diagnose
from app.agent.validator import ActionBudget, validate
from app.guards.evidence_gate import EvidenceGateConfig
from app.schemas.eval import EvalCase
from app.schemas.retrieval import RetrievalOptions
from app.workflow.orchestrator import run_trust_gated_pass
from app.workflow.state import RetrievalPassResult


@dataclass
class AgentLoopResult:
    first_pass: RetrievalPassResult
    final_pass: RetrievalPassResult
    action_trajectory: list[dict[str, Any]] = field(default_factory=list)
    budget_consumed: int = 0
    terminal_reason: str = "refuse"
    actual_rewritten_query: str | None = None
    second_pass_attempted: bool = False

    @property
    def trace_fields(self) -> dict[str, Any]:
        return {
            "agent_version": "v2",
            "controller_source": "rule",
            "action_trajectory": self.action_trajectory,
            "budget_consumed": self.budget_consumed,
            "terminal_reason": self.terminal_reason,
        }


def run_agentic_v2_loop(
    *,
    case: EvalCase,
    retriever,
    reranker,
    retrieval_options: RetrievalOptions,
    evidence_gate_config: EvidenceGateConfig | None = None,
    controller: RuleController | None = None,
    budget: ActionBudget | None = None,
    max_steps: int = 3,
) -> AgentLoopResult:
    selected_controller = controller or RuleController()
    current_budget = budget or ActionBudget()
    first_pass = run_trust_gated_pass(
        query=case.query,
        retrieval_options=retrieval_options,
        retriever=retriever,
        reranker=reranker,
        user_role=case.user_role,
        user_department=case.user_department,
        user_clearance=case.user_clearance.value,
        evidence_gate_config=evidence_gate_config,
    )
    current_pass = first_pass
    trajectory: list[dict[str, Any]] = []
    actual_rewritten_query: str | None = None

    for step in range(1, max_steps + 1):
        diagnosis = diagnose(current_pass)
        if diagnosis.evidence_decision == "sufficient":
            return AgentLoopResult(
                first_pass=first_pass,
                final_pass=current_pass,
                action_trajectory=trajectory,
                budget_consumed=current_budget.consumed_nonterminal_actions,
                terminal_reason="answer",
                actual_rewritten_query=actual_rewritten_query,
                second_pass_attempted=current_budget.consumed_nonterminal_actions > 0,
            )

        proposal = selected_controller.select(diagnosis)
        proposal = materialize_proposal(
            proposal,
            query=current_pass.query,
            pass_result=current_pass,
        )
        validation = validate(proposal, diagnosis, current_budget)
        trace_row = _trace_row(
            step=step,
            diagnosis=diagnosis,
            proposal=proposal,
            validator_ok=validation.ok,
            validator_reject_reason=validation.reject_reason,
        )

        if not validation.ok:
            trace_row["post_action_evidence_decision"] = diagnosis.evidence_decision
            trajectory.append(trace_row)
            return AgentLoopResult(
                first_pass=first_pass,
                final_pass=current_pass,
                action_trajectory=trajectory,
                budget_consumed=current_budget.consumed_nonterminal_actions,
                terminal_reason=_terminal_from_reject(validation.reject_reason),
                actual_rewritten_query=actual_rewritten_query,
                second_pass_attempted=current_budget.consumed_nonterminal_actions > 0,
            )

        if proposal.action in {
            ActionType.present_conflict_set,
            ActionType.refuse_with_explanation,
        }:
            trace_row["post_action_evidence_decision"] = diagnosis.evidence_decision
            trajectory.append(trace_row)
            return AgentLoopResult(
                first_pass=first_pass,
                final_pass=current_pass,
                action_trajectory=trajectory,
                budget_consumed=current_budget.consumed_nonterminal_actions,
                terminal_reason=(
                    "conflict_set"
                    if proposal.action == ActionType.present_conflict_set
                    else "refuse"
                ),
                actual_rewritten_query=actual_rewritten_query,
                second_pass_attempted=current_budget.consumed_nonterminal_actions > 0,
            )

        action_result = execute_action(
            proposal,
            current_pass.query,
            retriever,
            reranker,
            settings=None,
            retrieval_options=retrieval_options,
            evidence_gate_config=evidence_gate_config,
            user_role=case.user_role,
            user_department=case.user_department,
            user_clearance=case.user_clearance.value,
        )
        if action_result.pass_result is None:
            trace_row["post_action_evidence_decision"] = diagnosis.evidence_decision
            trajectory.append(trace_row)
            return AgentLoopResult(
                first_pass=first_pass,
                final_pass=current_pass,
                action_trajectory=trajectory,
                budget_consumed=current_budget.consumed_nonterminal_actions,
                terminal_reason=action_result.terminal_reason or "refuse",
                actual_rewritten_query=actual_rewritten_query,
                second_pass_attempted=current_budget.consumed_nonterminal_actions > 0,
            )

        current_pass = action_result.pass_result
        if proposal.action == ActionType.rewrite_query:
            actual_rewritten_query = current_pass.query
        current_budget = current_budget.consume(proposal.action)
        trace_row["post_action_evidence_decision"] = diagnose(current_pass).evidence_decision
        trajectory.append(trace_row)

    return AgentLoopResult(
        first_pass=first_pass,
        final_pass=current_pass,
        action_trajectory=trajectory,
        budget_consumed=current_budget.consumed_nonterminal_actions,
        terminal_reason="budget_exhausted",
        actual_rewritten_query=actual_rewritten_query,
        second_pass_attempted=current_budget.consumed_nonterminal_actions > 0,
    )


def _trace_row(
    *,
    step: int,
    diagnosis: DiagnosisReport,
    proposal: ActionProposal,
    validator_ok: bool,
    validator_reject_reason: str | None,
) -> dict[str, Any]:
    row = {
        "step": step,
        "diagnosis_failure_type": diagnosis.failure_type.value,
        "legal_actions": [action.value for action in diagnosis.legal_actions],
        "chosen_action": proposal.action.value,
        "action_source": proposal.source,
        "validator_ok": validator_ok,
    }
    if validator_reject_reason:
        row["validator_reject_reason"] = validator_reject_reason
    return row


def _terminal_from_reject(reject_reason: str | None) -> str:
    if reject_reason == "budget_exhausted":
        return "budget_exhausted"
    return "refuse"
