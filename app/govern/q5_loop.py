"""Bounded Q5 observation loop shared by rule, LLM, and hybrid agents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.govern.conditions import ActorContext, ConditionReport, GovernanceAction, OpsCondition
from app.govern.executor import execute_governance_action
from app.govern.q5_context import (
    Q5AuthorizationVerdict,
    Q5DecisionContext,
    Q5ProposalKind,
    Q5StructuredProposal,
    Q5TrustedObservation,
    build_q5_context_trace,
    build_q5_decision_context,
    reauthorize_q5_proposal,
)
from app.govern.q5_environment import Q5ReadOnlyEnvironment
from app.govern.q5_llm_policy import Q5LLMAgentPolicy
from app.govern.q5_policy import Q5AgentPolicy, Q5PolicyModel
from app.govern.q5_router import (
    Q5MissingStateType,
    Q5RouteDecision,
    Q5RouteFacts,
    Q5RouteReason,
    route_q5,
)
from app.govern.q5_rule_policy import Q5RuleAgentPolicy
from app.govern.q5_tool_validator import (
    q5_allowed_tool_argument_values,
    validate_q5_tool_call,
)
from app.govern.q5_tools import Q5ToolEvent, Q5ToolExecutor, Q5ToolStatus
from app.govern.sinks import ActionRecord, ActionSink
from app.govern.validator import (
    GovernanceBudget,
    GovernanceProposal,
    GovValidationResult,
    legal_actions_for_report,
    validate_governance,
)
from app.guards.acl_gate import ACLGateDecision
from app.schemas.q5_task import Q5ObservationTool, Q5TaskInput
from app.workflow.state import RetrievalPassResult


class Q5AgentSystem(StrEnum):
    rule = "q5_rule_agent"
    llm = "q5_llm_agent"
    hybrid = "q5_hybrid_agent"


class Q5TrajectoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_index: int = Field(ge=1, le=3)
    context_version: int = Field(ge=1)
    event_type: Literal[
        "policy_error",
        "tool_rejected",
        "observation",
        "terminal",
    ]
    policy_source: Literal["rule", "llm"]
    reason_code: str
    proposal_kind: Q5ProposalKind | None = None
    tool: Q5ObservationTool | None = None
    tool_status: Q5ToolStatus | None = None
    action: GovernanceAction | None = None
    authorization_reason: str | None = None
    q4_validator_verdict: Literal["accepted", "rejected", "not_run"] = "not_run"
    q4_validator_reject_reason: str | None = None


class Q5AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    system: Q5AgentSystem
    route: Q5RouteDecision
    terminal_proposal: Q5StructuredProposal
    final_action: GovernanceAction
    q4_validation: GovValidationResult
    record: ActionRecord | None = None
    tool_events: list[Q5ToolEvent] = Field(default_factory=list)
    otel_spans: list[dict] = Field(default_factory=list)
    trajectory: list[Q5TrajectoryEvent] = Field(default_factory=list)
    context_traces: list[dict] = Field(default_factory=list)
    observation_count: int = Field(ge=0, le=2)
    terminal_proposal_count: Literal[1] = 1
    step_count: int = Field(ge=1, le=3)
    llm_calls: int = Field(ge=0)
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def _validate_bounded_result(self) -> Q5AgentResult:
        if self.observation_count != len(self.tool_events):
            raise ValueError("observation_count must match tool events")
        if self.step_count != self.observation_count + self.terminal_proposal_count:
            raise ValueError("step count must equal observation plus terminal count")
        return self


@dataclass(frozen=True)
class Q5AgentRuntime:
    """Shared dependency surface; policy arms cannot swap tools, env, validator, or sink."""

    environment: Q5ReadOnlyEnvironment
    sink: ActionSink
    model: Q5PolicyModel | None = None


@dataclass
class _LoopState:
    observations: list[Q5TrustedObservation]
    tool_events: list[Q5ToolEvent]
    spans: list[dict]
    trajectory: list[Q5TrajectoryEvent]
    context_traces: list[dict]
    llm_calls: int = 0


def run_q5_agent(
    *,
    system: Q5AgentSystem,
    task: Q5TaskInput,
    pass_result: RetrievalPassResult,
    report: ConditionReport,
    runtime: Q5AgentRuntime,
) -> Q5AgentResult:
    """Run one bounded Q5 trajectory. No gold object is accepted by this API."""

    if task.environment_ref != runtime.environment.environment_ref:
        raise ValueError("task environment_ref does not match Q5 runtime environment")

    condition_legal_actions = legal_actions_for_report(report)
    max_observations = min(task.max_observation_steps, 2)
    context = _build_context(
        task,
        pass_result,
        report,
        condition_legal_actions,
        observations=[],
        remaining_observations=max_observations,
    )
    route_facts = _route_facts(task, context)
    route, policy = _select_policy(system, route_facts, runtime.model)
    state = _LoopState(
        observations=[],
        tool_events=[],
        spans=[],
        trajectory=[],
        context_traces=[build_q5_context_trace(context, context_version=1)],
    )
    tool_executor = Q5ToolExecutor(runtime.environment)
    context_version = 1

    for step_index in range(1, 4):
        policy_step = policy.decide(context)
        state.llm_calls += int(policy_step.llm_called)
        if policy_step.proposal is None:
            reason = policy_step.error_reason or policy_step.parse_status
            state.trajectory.append(
                Q5TrajectoryEvent(
                    step_index=step_index,
                    context_version=context_version,
                    event_type="policy_error",
                    policy_source=policy_step.policy_source,
                    reason_code=reason,
                )
            )
            return _finalize(
                system=system,
                route=route,
                task=task,
                pass_result=pass_result,
                report=report,
                runtime=runtime,
                context=context,
                state=state,
                proposal=_safe_escalation(context, "policy_error"),
                policy_source=policy_step.policy_source,
                step_index=step_index,
                context_version=context_version,
                fallback_reason=reason,
            )

        proposal = policy_step.proposal
        if proposal.kind is Q5ProposalKind.terminal:
            return _finalize(
                system=system,
                route=route,
                task=task,
                pass_result=pass_result,
                report=report,
                runtime=runtime,
                context=context,
                state=state,
                proposal=proposal,
                policy_source=policy_step.policy_source,
                step_index=step_index,
                context_version=context_version,
            )

        if len(state.observations) >= max_observations:
            state.trajectory.append(
                Q5TrajectoryEvent(
                    step_index=step_index,
                    context_version=context_version,
                    event_type="tool_rejected",
                    policy_source=policy_step.policy_source,
                    reason_code="observation_budget_exhausted",
                    proposal_kind=proposal.kind,
                    tool=proposal.tool,
                )
            )
            return _finalize(
                system=system,
                route=route,
                task=task,
                pass_result=pass_result,
                report=report,
                runtime=runtime,
                context=context,
                state=state,
                proposal=_safe_escalation(context, "budget_exhausted"),
                policy_source=policy_step.policy_source,
                step_index=step_index,
                context_version=context_version,
                fallback_reason="observation_budget_exhausted",
            )

        authorization = reauthorize_q5_proposal(
            proposal,
            actor_claims=task.actor,
            requested_capability=task.requested_capability,
            available_tools=task.available_tools,
        )
        if not authorization.allowed:
            return _reject_tool_and_escalate(
                reason=f"observation_{authorization.reason_code}",
                system=system,
                route=route,
                task=task,
                pass_result=pass_result,
                report=report,
                runtime=runtime,
                context=context,
                state=state,
                proposal=proposal,
                policy_source=policy_step.policy_source,
                step_index=step_index,
                context_version=context_version,
                authorization=authorization,
            )

        assert proposal.tool is not None
        tool_validation = validate_q5_tool_call(
            tool=proposal.tool,
            args=proposal.args,
            task=task,
            context=context,
        )
        if not tool_validation.allowed or tool_validation.call is None:
            return _reject_tool_and_escalate(
                reason=f"tool_{tool_validation.reason_code}",
                system=system,
                route=route,
                task=task,
                pass_result=pass_result,
                report=report,
                runtime=runtime,
                context=context,
                state=state,
                proposal=proposal,
                policy_source=policy_step.policy_source,
                step_index=step_index,
                context_version=context_version,
                authorization=authorization,
            )

        execution = tool_executor.execute(tool_validation.call)
        state.tool_events.append(execution.event)
        state.spans.append(execution.span_payload)
        trusted_observation = execution.result.trusted_context_slice()
        state.observations.append(trusted_observation)
        state.trajectory.append(
            Q5TrajectoryEvent(
                step_index=step_index,
                context_version=context_version,
                event_type="observation",
                policy_source=policy_step.policy_source,
                reason_code=f"tool_{execution.result.status.value}",
                proposal_kind=proposal.kind,
                tool=proposal.tool,
                tool_status=execution.result.status,
                authorization_reason=authorization.reason_code,
            )
        )

        context = _build_context(
            task,
            pass_result,
            report,
            condition_legal_actions,
            observations=state.observations,
            remaining_observations=max_observations - len(state.observations),
        )
        context_version += 1
        state.context_traces.append(
            build_q5_context_trace(context, context_version=context_version)
        )
        if execution.result.status in {Q5ToolStatus.timeout, Q5ToolStatus.invalid}:
            return _finalize(
                system=system,
                route=route,
                task=task,
                pass_result=pass_result,
                report=report,
                runtime=runtime,
                context=context,
                state=state,
                proposal=_safe_escalation(context, "tool_failure"),
                policy_source=policy_step.policy_source,
                step_index=step_index,
                context_version=context_version,
                fallback_reason=f"tool_{execution.result.status.value}",
            )

    return _finalize(
        system=system,
        route=route,
        task=task,
        pass_result=pass_result,
        report=report,
        runtime=runtime,
        context=context,
        state=state,
        proposal=_safe_escalation(context, "step_budget_exhausted"),
        policy_source=policy.policy_source,
        step_index=3,
        context_version=context_version,
        fallback_reason="step_budget_exhausted",
    )


def _select_policy(
    system: Q5AgentSystem,
    facts: Q5RouteFacts,
    model: Q5PolicyModel | None,
) -> tuple[Q5RouteDecision, Q5AgentPolicy]:
    rule = Q5RuleAgentPolicy()
    llm = Q5LLMAgentPolicy(model)
    if system is Q5AgentSystem.rule:
        return _fixed_route("rule", Q5RouteReason.rule_baseline, facts), rule
    if facts.terminal_policy_block:
        return _fixed_route("rule", Q5RouteReason.terminal_policy_block, facts), rule
    if system is Q5AgentSystem.llm:
        return _fixed_route("llm", Q5RouteReason.always_llm_control, facts), llm
    decision = route_q5(facts)
    return decision, llm if decision.route == "llm" else rule


def _fixed_route(
    route: Literal["rule", "llm"],
    reason: Q5RouteReason,
    facts: Q5RouteFacts,
) -> Q5RouteDecision:
    return Q5RouteDecision(
        route=route,
        route_reasons=[reason],
        observable_ambiguity_count=facts.observable_ambiguity_count,
        missing_state_types=list(facts.missing_state_types),
        candidate_terminal_actions=list(facts.candidate_terminal_actions),
    )


def _route_facts(task: Q5TaskInput, context: Q5DecisionContext) -> Q5RouteFacts:
    terminal_block = (
        OpsCondition.permission_blocked in context.conditions
        or OpsCondition.insufficient_evidence in context.conditions
        or context.evidence_decision == "insufficient"
        or context.legal_terminal_actions == [GovernanceAction.escalate_to_human]
    )
    observed_tools = {observation.tool_name for observation in context.observations}
    references = set(q5_allowed_tool_argument_values(task=task, context=context))
    missing: list[Q5MissingStateType] = []
    if (
        any(
            condition in context.conditions
            for condition in (OpsCondition.config_violation, OpsCondition.policy_violation)
        )
        and Q5ObservationTool.lookup_policy_exception in task.available_tools
        and Q5ObservationTool.lookup_policy_exception not in observed_tools
        and any(value.startswith("resource:") for value in references)
        and any(value.startswith("policy:") for value in references)
    ):
        missing.append(Q5MissingStateType.policy_exception)
    if (
        any(
            condition in context.conditions
            for condition in (OpsCondition.stale_procedure, OpsCondition.missing_prereq)
        )
        and Q5ObservationTool.inspect_change_state in task.available_tools
        and Q5ObservationTool.inspect_change_state not in observed_tools
        and any(value.startswith("change:") for value in references)
    ):
        missing.append(Q5MissingStateType.change_state)
    if (
        OpsCondition.active_active_conflict in context.conditions
        and Q5ObservationTool.inspect_incident_impact in task.available_tools
        and Q5ObservationTool.inspect_incident_impact not in observed_tools
        and any(value.startswith("resource:") for value in references)
    ):
        missing.append(Q5MissingStateType.incident_impact)
    return Q5RouteFacts(
        terminal_policy_block=terminal_block,
        structured_state_complete=not terminal_block and not missing,
        observable_ambiguity_count=len(missing),
        missing_state_types=missing,
        candidate_terminal_actions=list(context.legal_terminal_actions),
    )


def _build_context(
    task: Q5TaskInput,
    pass_result: RetrievalPassResult,
    report: ConditionReport,
    condition_legal_actions: list[GovernanceAction],
    *,
    observations: list[Q5TrustedObservation],
    remaining_observations: int,
) -> Q5DecisionContext:
    return build_q5_decision_context(
        pass_result,
        actor_claims=task.actor,
        requested_capability=task.requested_capability,
        resource_refs=task.resource_refs,
        available_tools=task.available_tools,
        conditions=report.conditions,
        evidence_decision=report.evidence_decision,
        condition_legal_actions=condition_legal_actions,
        observations=observations,
        remaining_observation_budget=remaining_observations,
        remaining_terminal_budget=1,
    )


def _reject_tool_and_escalate(
    *,
    reason: str,
    system: Q5AgentSystem,
    route: Q5RouteDecision,
    task: Q5TaskInput,
    pass_result: RetrievalPassResult,
    report: ConditionReport,
    runtime: Q5AgentRuntime,
    context: Q5DecisionContext,
    state: _LoopState,
    proposal: Q5StructuredProposal,
    policy_source: Literal["rule", "llm"],
    step_index: int,
    context_version: int,
    authorization: Q5AuthorizationVerdict,
) -> Q5AgentResult:
    state.trajectory.append(
        Q5TrajectoryEvent(
            step_index=step_index,
            context_version=context_version,
            event_type="tool_rejected",
            policy_source=policy_source,
            reason_code=reason,
            proposal_kind=proposal.kind,
            tool=proposal.tool,
            authorization_reason=authorization.reason_code,
        )
    )
    return _finalize(
        system=system,
        route=route,
        task=task,
        pass_result=pass_result,
        report=report,
        runtime=runtime,
        context=context,
        state=state,
        proposal=_safe_escalation(context, "tool_rejected"),
        policy_source=policy_source,
        step_index=step_index,
        context_version=context_version,
        fallback_reason=reason,
    )


def _finalize(
    *,
    system: Q5AgentSystem,
    route: Q5RouteDecision,
    task: Q5TaskInput,
    pass_result: RetrievalPassResult,
    report: ConditionReport,
    runtime: Q5AgentRuntime,
    context: Q5DecisionContext,
    state: _LoopState,
    proposal: Q5StructuredProposal,
    policy_source: Literal["rule", "llm"],
    step_index: int,
    context_version: int,
    fallback_reason: str | None = None,
) -> Q5AgentResult:
    terminal_step_index = min(3, max(step_index, len(state.tool_events) + 1))
    effective = proposal
    authorized_ids = {item.chunk_id for item in context.authorized_evidence}
    if not set(proposal.evidence_chunk_ids).issubset(authorized_ids):
        fallback_reason = fallback_reason or "invalid_evidence_citation"
        effective = _safe_escalation(context, "invalid_citation")
    elif proposal.action not in context.legal_terminal_actions:
        fallback_reason = fallback_reason or "illegal_terminal_action"
        effective = _safe_escalation(context, "illegal_action")

    authorization = reauthorize_q5_proposal(
        effective,
        actor_claims=task.actor,
        requested_capability=task.requested_capability,
        available_tools=task.available_tools,
    )
    if not authorization.allowed:
        fallback_reason = fallback_reason or f"reauthorization_{authorization.reason_code}"
        effective = _safe_escalation(context, "reauthorization_failed")
        authorization = reauthorize_q5_proposal(
            effective,
            actor_claims=task.actor,
            requested_capability=task.requested_capability,
            available_tools=task.available_tools,
        )

    assert effective.action is not None
    proposal_report = report.model_copy(update={"authorized_actor": authorization.allowed})
    q4_proposal = GovernanceProposal(
        action=effective.action,
        args={"evidence_citations": effective.evidence_chunk_ids},
        source=system.value,
        reason=effective.reason_summary,
        controller_source=system.value,
    )
    if effective.action is GovernanceAction.no_op and not proposal_report.conditions:
        q4_validation = GovValidationResult(ok=True)
    else:
        q4_validation = validate_governance(
            q4_proposal,
            proposal_report,
            GovernanceBudget(max_actions=1),
        )

    final_action = effective.action
    if not q4_validation.ok:
        final_action = q4_validation.forced_action or GovernanceAction.escalate_to_human
        fallback_reason = fallback_reason or f"q4_validator_{q4_validation.reject_reason}"

    record = None
    if final_action is not GovernanceAction.no_op:
        record = execute_governance_action(
            final_action,
            proposal_report,
            _authorized_execution_pass(pass_result),
            ActorContext(
                role=task.actor.role,
                clearance=task.actor.clearance,
                department=task.actor.department,
                requested_action=final_action,
            ),
            runtime.sink,
            evidence_citations=effective.evidence_chunk_ids,
        )

    state.trajectory.append(
        Q5TrajectoryEvent(
            step_index=terminal_step_index,
            context_version=context_version,
            event_type="terminal",
            policy_source=policy_source,
            reason_code=fallback_reason or effective.reason_code,
            proposal_kind=Q5ProposalKind.terminal,
            action=final_action,
            authorization_reason=authorization.reason_code,
            q4_validator_verdict="accepted" if q4_validation.ok else "rejected",
            q4_validator_reject_reason=q4_validation.reject_reason,
        )
    )
    return Q5AgentResult(
        system=system,
        route=route,
        terminal_proposal=effective,
        final_action=final_action,
        q4_validation=q4_validation,
        record=record,
        tool_events=list(state.tool_events),
        otel_spans=list(state.spans),
        trajectory=list(state.trajectory),
        context_traces=list(state.context_traces),
        observation_count=len(state.tool_events),
        terminal_proposal_count=1,
        step_count=terminal_step_index,
        llm_calls=state.llm_calls,
        fallback_reason=fallback_reason,
    )


def _safe_escalation(
    context: Q5DecisionContext,
    reason_code: str,
) -> Q5StructuredProposal:
    return Q5StructuredProposal(
        kind=Q5ProposalKind.terminal,
        tool=None,
        args={},
        action=GovernanceAction.escalate_to_human,
        evidence_chunk_ids=[item.chunk_id for item in context.authorized_evidence[:5]],
        reason_code=reason_code,
        reason_summary="The bounded Q5 loop stopped safely and escalated for review.",
    )


def _authorized_execution_pass(pass_result: RetrievalPassResult) -> RetrievalPassResult:
    surviving = list(pass_result.acl_decision.surviving_chunks)
    authorized_ids = {result.chunk.chunk_id for result in surviving}
    state_decision = pass_result.state_decision.model_copy(
        update={
            "surviving_chunks": [
                item
                for item in pass_result.state_decision.surviving_chunks
                if item.chunk.chunk_id in authorized_ids
            ],
            "deprecated_chunks": [
                item
                for item in pass_result.state_decision.deprecated_chunks
                if item.chunk.chunk_id in authorized_ids
            ],
            "blocked_chunks": [],
        }
    )
    conflict_chunks = [
        item
        for item in pass_result.conflict_decision.conflicting_chunks
        if item.chunk.chunk_id in authorized_ids
    ]
    conflict_decision = pass_result.conflict_decision.model_copy(
        update={
            "has_conflict": bool(conflict_chunks),
            "conflicting_chunks": conflict_chunks,
        }
    )
    return pass_result.model_copy(
        update={
            "retrieved_chunks": surviving,
            "reranked_chunks": surviving,
            "state_decision": state_decision,
            "acl_decision": ACLGateDecision(surviving_chunks=surviving),
            "conflict_decision": conflict_decision,
        }
    )
