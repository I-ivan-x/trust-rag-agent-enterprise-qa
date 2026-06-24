from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.actions import ActionProposal, execute_action, materialize_proposal
from app.agent.controller import ControllerContext, RuleController
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
    controller_source: str = "rule"

    @property
    def trace_fields(self) -> dict[str, Any]:
        action_sequence = [row["chosen_action"] for row in self.action_trajectory]
        validator_rejections = [
            {
                "step": row["step"],
                "action": row["chosen_action"],
                "reason": row["validator_reject_reason"],
                "controller_source": row["controller_source"],
            }
            for row in self.action_trajectory
            if row.get("validator_reject_reason")
        ]
        action_outcomes = [
            {
                "step": row["step"],
                "action": row["chosen_action"],
                "trigger": row["diagnosis_failure_type"],
                "outcome": row.get("action_outcome"),
            }
            for row in self.action_trajectory
        ]
        return {
            "agent_version": "v2",
            "controller_source": self.controller_source,
            "action_sequence": action_sequence,
            "action_trajectory": self.action_trajectory,
            "budget_consumed": self.budget_consumed,
            "validator_rejections": validator_rejections,
            "action_outcomes": action_outcomes,
            "terminal_reason": self.terminal_reason,
        }


def run_agentic_v2_loop(
    *,
    case: EvalCase,
    retriever,
    reranker,
    retrieval_options: RetrievalOptions,
    evidence_gate_config: EvidenceGateConfig | None = None,
    controller: Any | None = None,
    budget: ActionBudget | None = None,
    max_steps: int = 3,
) -> AgentLoopResult:
    selected_controller = controller or RuleController()
    controller_source = _controller_source(selected_controller)
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
    bounded_max_steps = min(max_steps, 3)

    for step in range(1, bounded_max_steps + 1):
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
                controller_source=controller_source,
            )

        context = _controller_context(current_pass)
        proposal = selected_controller.select(diagnosis, context)
        proposal = materialize_proposal(
            proposal,
            query=current_pass.query,
            pass_result=current_pass,
        )
        validation = validate(proposal, diagnosis, current_budget)

        if not validation.ok and proposal.source == "llm":
            reject_reason = validation.reject_reason or "unknown"
            proposal = _fallback_to_rule_after_validator_reject(
                diagnosis=diagnosis,
                context=context,
                query=current_pass.query,
                pass_result=current_pass,
                raw_llm_proposal=proposal,
                fallback_reason=f"validator_reject:{reject_reason}",
            )
            validation = validate(proposal, diagnosis, current_budget)

        trace_row = _trace_row(
            step=step,
            diagnosis=diagnosis,
            proposal=proposal,
            validator_ok=validation.ok,
            validator_reject_reason=validation.reject_reason,
            budget=current_budget,
        )

        if not validation.ok:
            trace_row["post_action_evidence_decision"] = diagnosis.evidence_decision
            trace_row["action_outcome"] = "validator_rejected"
            trace_row["budget_after"] = current_budget.consumed_nonterminal_actions
            trajectory.append(trace_row)
            return AgentLoopResult(
                first_pass=first_pass,
                final_pass=current_pass,
                action_trajectory=trajectory,
                budget_consumed=current_budget.consumed_nonterminal_actions,
                terminal_reason=_terminal_from_reject(validation.reject_reason),
                actual_rewritten_query=actual_rewritten_query,
                second_pass_attempted=current_budget.consumed_nonterminal_actions > 0,
                controller_source=controller_source,
            )

        if proposal.action in {
            ActionType.present_conflict_set,
            ActionType.refuse_with_explanation,
        }:
            trace_row["post_action_evidence_decision"] = diagnosis.evidence_decision
            trace_row["action_outcome"] = (
                "conflict_set"
                if proposal.action == ActionType.present_conflict_set
                else "refuse"
            )
            trace_row["budget_after"] = current_budget.consumed_nonterminal_actions
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
                controller_source=controller_source,
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
            trace_row["action_outcome"] = action_result.terminal_reason or "refuse"
            trace_row["budget_after"] = current_budget.consumed_nonterminal_actions
            trajectory.append(trace_row)
            return AgentLoopResult(
                first_pass=first_pass,
                final_pass=current_pass,
                action_trajectory=trajectory,
                budget_consumed=current_budget.consumed_nonterminal_actions,
                terminal_reason=action_result.terminal_reason or "refuse",
                actual_rewritten_query=actual_rewritten_query,
                second_pass_attempted=current_budget.consumed_nonterminal_actions > 0,
                controller_source=controller_source,
            )

        current_pass = action_result.pass_result
        if proposal.action == ActionType.rewrite_query:
            actual_rewritten_query = current_pass.query
        current_budget = current_budget.consume(proposal.action)
        post_action_diagnosis = diagnose(current_pass)
        trace_row["post_action_evidence_decision"] = (
            post_action_diagnosis.evidence_decision
        )
        trace_row["action_outcome"] = (
            "evidence_sufficient"
            if post_action_diagnosis.evidence_decision == "sufficient"
            else "evidence_insufficient"
        )
        trace_row["budget_after"] = current_budget.consumed_nonterminal_actions
        trajectory.append(trace_row)

    return AgentLoopResult(
        first_pass=first_pass,
        final_pass=current_pass,
        action_trajectory=trajectory,
        budget_consumed=current_budget.consumed_nonterminal_actions,
        terminal_reason="budget_exhausted",
        actual_rewritten_query=actual_rewritten_query,
        second_pass_attempted=current_budget.consumed_nonterminal_actions > 0,
        controller_source=controller_source,
    )


def _trace_row(
    *,
    step: int,
    diagnosis: DiagnosisReport,
    proposal: ActionProposal,
    validator_ok: bool,
    validator_reject_reason: str | None,
    budget: ActionBudget,
) -> dict[str, Any]:
    fallback_reject_reason = None
    if proposal.fallback_reason and proposal.fallback_reason.startswith(
        "validator_reject:"
    ):
        fallback_reject_reason = proposal.fallback_reason.removeprefix(
            "validator_reject:"
        )
    row = {
        "step": step,
        "diagnosis_failure_type": diagnosis.failure_type.value,
        "legal_actions": [action.value for action in diagnosis.legal_actions],
        "controller_source": proposal.controller_source or _source_to_controller(
            proposal.source
        ),
        "llm_raw_proposal": proposal.llm_raw_proposal,
        "accepted": proposal.accepted,
        "fallback_reason": proposal.fallback_reason,
        "chosen_action": proposal.action.value,
        "chosen_source": proposal.source,
        "action_source": proposal.source,
        "reason": proposal.reason,
        "validator_ok": validator_ok,
        "action_triggered": proposal.action in diagnosis.legal_actions,
        "budget_before": budget.consumed_nonterminal_actions,
    }
    reject_reason = validator_reject_reason or fallback_reject_reason
    if reject_reason:
        row["validator_reject_reason"] = reject_reason
    return row


def _terminal_from_reject(reject_reason: str | None) -> str:
    if reject_reason == "budget_exhausted":
        return "budget_exhausted"
    return "refuse"


def _controller_source(controller: Any) -> str:
    return str(getattr(controller, "controller_source", "rule"))


def _source_to_controller(source: str) -> str:
    if source.startswith("llm"):
        return "llm"
    return "rule"


def _controller_context(pass_result: RetrievalPassResult) -> ControllerContext:
    return ControllerContext(
        query=pass_result.query,
        neighborhood=[
            {
                "doc_id": item.chunk.doc_id,
                "chunk_id": item.chunk.chunk_id,
                "title": item.chunk.section_path[0]
                if item.chunk.section_path
                else item.chunk.doc_id,
                "status": item.chunk.status.value,
                "access_level": item.chunk.access_level.value,
                "rerank_score": item.rerank_score,
                "rank": item.rank,
            }
            for item in pass_result.reranked_chunks[:5]
        ],
    )


def _fallback_to_rule_after_validator_reject(
    *,
    diagnosis: DiagnosisReport,
    context: ControllerContext,
    query: str,
    pass_result: RetrievalPassResult,
    raw_llm_proposal: ActionProposal,
    fallback_reason: str,
) -> ActionProposal:
    fallback = RuleController().select(diagnosis, context)
    raw_proposal = raw_llm_proposal.llm_raw_proposal or {
        "action": raw_llm_proposal.action.value,
        "args": raw_llm_proposal.args,
        "reason": raw_llm_proposal.reason,
    }
    fallback = fallback.model_copy(
        update={
            "source": "llm_fallback_rule",
            "controller_source": "llm",
            "llm_raw_proposal": raw_proposal,
            "accepted": False,
            "fallback_reason": fallback_reason,
            "reason": raw_llm_proposal.reason,
        }
    )
    return materialize_proposal(
        fallback,
        query=query,
        pass_result=pass_result,
    )
