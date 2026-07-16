"""Bounded Q5 observation loop shared by rule, LLM, and hybrid agents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.govern.conditions import ActorContext, ConditionReport, GovernanceAction, OpsCondition
from app.govern.executor import execute_governance_action
from app.govern.q5_context import (
    Q5AuthorizationVerdict,
    Q5DecisionContext,
    Q5PolicyDisposition,
    Q5ProposalKind,
    Q5StructuredProposal,
    Q5TrustedObservation,
    build_q5_context_trace,
    build_q5_decision_context,
    reauthorize_q5_proposal,
)
from app.govern.q5_environment import Q5ReadOnlyEnvironment
from app.govern.q5_fallback import (
    Q5_FALLBACK_RESULT_REASON,
    Q5_FALLBACK_TERMINAL_REASON_CODE,
    Q5_TOOL_VALIDATION_FALLBACK,
    Q5FallbackCause,
)
from app.govern.q5_llm_policy import Q5LLMAgentPolicy
from app.govern.q5_policy import (
    Q5AgentPolicy,
    Q5PolicyDecisionEvent,
    Q5PolicyModel,
)
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
    q5_completed_observation_key,
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


_SIDE_EFFECT_ACTIONS = frozenset(
    {
        GovernanceAction.flag_stale,
        GovernanceAction.open_remediation_ticket,
        GovernanceAction.send_alert,
    }
)
_DYNAMIC_STATE_REQUIREMENTS = (
    (
        frozenset({OpsCondition.config_violation, OpsCondition.policy_violation}),
        Q5ObservationTool.lookup_policy_exception,
    ),
    (
        frozenset({OpsCondition.stale_procedure, OpsCondition.missing_prereq}),
        Q5ObservationTool.inspect_change_state,
    ),
    (
        frozenset({OpsCondition.active_active_conflict}),
        Q5ObservationTool.inspect_incident_impact,
    ),
)


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
    policy_disposition: Q5PolicyDisposition | None = None
    disposition_source: Literal["model", "rule", "fallback"] | None = None
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
    q4_validation_input: dict[str, Any]
    record: ActionRecord | None = None
    tool_events: list[Q5ToolEvent] = Field(default_factory=list)
    policy_events: list[Q5PolicyDecisionEvent] = Field(default_factory=list)
    otel_spans: list[dict] = Field(default_factory=list)
    trajectory: list[Q5TrajectoryEvent] = Field(default_factory=list)
    context_traces: list[dict] = Field(default_factory=list)
    observation_count: int = Field(ge=0, le=2)
    terminal_proposal_count: Literal[1] = 1
    step_count: int = Field(ge=1, le=3)
    llm_calls: int = Field(ge=0)
    duplicate_successful_observation_count: int = Field(ge=0)
    post_observation_terminal_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def _validate_bounded_result(self) -> Q5AgentResult:
        if self.observation_count != len(self.tool_events):
            raise ValueError("observation_count must match tool events")
        if self.step_count != self.observation_count + self.terminal_proposal_count:
            raise ValueError("step count must equal observation plus terminal count")
        expected_policy_steps = list(range(1, len(self.policy_events) + 1))
        if [event.step_index for event in self.policy_events] != expected_policy_steps:
            raise ValueError("policy event step indexes must be contiguous")
        if not self.policy_events or len(self.policy_events) > 3:
            raise ValueError("result must contain one to three policy events")
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
    policy_events: list[Q5PolicyDecisionEvent]
    spans: list[dict]
    trajectory: list[Q5TrajectoryEvent]
    context_traces: list[dict]
    completed_observation_keys: set[str]
    llm_calls: int = 0
    duplicate_successful_observation_count: int = 0
    terminal_only_prompt_count: int = 0
    terminal_selected_from_terminal_only: int = 0


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
        policy_events=[],
        spans=[],
        trajectory=[],
        context_traces=[build_q5_context_trace(context, context_version=1)],
        completed_observation_keys=set(),
    )
    tool_executor = Q5ToolExecutor(runtime.environment)
    context_version = 1

    for step_index in range(1, 4):
        if context.terminal_only:
            state.terminal_only_prompt_count += 1
        policy_step = policy.decide(context)
        state.llm_calls += int(policy_step.llm_called)
        state.policy_events.append(
            Q5PolicyDecisionEvent(
                step_index=step_index,
                context_version=context_version,
                policy_source=policy_step.policy_source,
                parse_status=policy_step.parse_status,
                error_reason=policy_step.error_reason,
                raw_payload_sha256=policy_step.raw_payload_sha256,
                accepted_proposal=policy_step.proposal,
                llm_called=policy_step.llm_called,
            )
        )
        if policy_step.proposal is None:
            fallback_cause = (
                Q5FallbackCause.policy_model_error
                if policy_step.parse_status == "model_error"
                else (
                    Q5FallbackCause.tool_schema_invalid
                    if policy_step.error_reason == "tool_schema_invalid"
                    else Q5FallbackCause.policy_parse_error
                )
            )
            state.trajectory.append(
                Q5TrajectoryEvent(
                    step_index=step_index,
                    context_version=context_version,
                    event_type="policy_error",
                    policy_source=policy_step.policy_source,
                    reason_code=fallback_cause.value,
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
                proposal=_safe_escalation(context, fallback_cause),
                policy_source=policy_step.policy_source,
                step_index=step_index,
                context_version=context_version,
                fallback_cause=fallback_cause,
            )

        proposal = policy_step.proposal
        if proposal.kind is Q5ProposalKind.terminal:
            if context.terminal_only:
                state.terminal_selected_from_terminal_only += 1
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

        authorization = reauthorize_q5_proposal(
            proposal,
            actor_claims=task.actor,
            requested_capability=task.requested_capability,
            available_tools=task.available_tools,
        )
        if not authorization.allowed:
            return _reject_tool_and_escalate(
                fallback_cause=Q5FallbackCause.observation_reauthorization_rejection,
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
                fallback_cause=Q5_TOOL_VALIDATION_FALLBACK[
                    tool_validation.reason_code
                ],
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

        completed_key = q5_completed_observation_key(
            tool_validation.call.tool,
            tool_validation.call.args,
        )
        if completed_key in state.completed_observation_keys:
            state.duplicate_successful_observation_count += 1
            return _reject_tool_and_escalate(
                fallback_cause=Q5FallbackCause.duplicate_successful_observation,
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
        if context.terminal_only:
            return _reject_tool_and_escalate(
                fallback_cause=Q5FallbackCause.terminal_only_observation_rejected,
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
        if len(state.observations) >= max_observations:
            return _reject_tool_and_escalate(
                fallback_cause=(
                    Q5FallbackCause.step_budget_exhausted
                    if step_index == 3
                    else Q5FallbackCause.observation_budget_exhausted
                ),
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
        if execution.result.status in {Q5ToolStatus.ok, Q5ToolStatus.not_found}:
            state.completed_observation_keys.add(completed_key)
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

        terminal_only = bool(q5_required_state_tools(context)) and not (
            q5_unresolved_state_tools(
                context.model_copy(update={"observations": state.observations})
            )
        )
        context = _build_context(
            task,
            pass_result,
            report,
            condition_legal_actions,
            observations=state.observations,
            remaining_observations=max_observations - len(state.observations),
            terminal_only=terminal_only,
        )
        context_version += 1
        state.context_traces.append(
            build_q5_context_trace(context, context_version=context_version)
        )
        if execution.result.status is Q5ToolStatus.invalid:
            fallback_cause = Q5FallbackCause.tool_invalid
            return _finalize(
                system=system,
                route=route,
                task=task,
                pass_result=pass_result,
                report=report,
                runtime=runtime,
                context=context,
                state=state,
                proposal=_safe_escalation(context, fallback_cause),
                policy_source=policy_step.policy_source,
                step_index=step_index,
                context_version=context_version,
                fallback_cause=fallback_cause,
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
        proposal=_safe_escalation(context, Q5FallbackCause.step_budget_exhausted),
        policy_source=policy.policy_source,
        step_index=3,
        context_version=context_version,
        fallback_cause=Q5FallbackCause.step_budget_exhausted,
    )


def _select_policy(
    system: Q5AgentSystem,
    facts: Q5RouteFacts,
    model: Q5PolicyModel | None,
) -> tuple[Q5RouteDecision, Q5AgentPolicy]:
    rule = Q5RuleAgentPolicy()
    llm = Q5LLMAgentPolicy(model)
    if facts.terminal_policy_block:
        return _fixed_route("rule", Q5RouteReason.terminal_policy_block, facts), rule
    if system is Q5AgentSystem.rule:
        return _fixed_route("rule", Q5RouteReason.rule_baseline, facts), rule
    if (
        facts.structured_state_complete
        and facts.candidate_terminal_actions == [GovernanceAction.escalate_to_human]
    ):
        return _fixed_route("rule", Q5RouteReason.trusted_state_complete, facts), rule
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
        candidate_terminal_actions=(
            [GovernanceAction.escalate_to_human]
            if terminal_block
            else list(context.legal_terminal_actions)
        ),
    )


def q5_required_state_tools(
    context: Q5DecisionContext,
) -> frozenset[Q5ObservationTool]:
    """Derive required observation types from runtime-visible facts only."""

    conditions = frozenset(context.conditions)
    available_tools = frozenset(context.available_tools)
    return frozenset(
        tool
        for triggering_conditions, tool in _DYNAMIC_STATE_REQUIREMENTS
        if conditions & triggering_conditions and tool in available_tools
    )


def q5_unresolved_state_tools(
    context: Q5DecisionContext,
) -> frozenset[Q5ObservationTool]:
    """Derive unresolved dynamic state from runtime-visible context facts only."""

    observed_tools = frozenset(
        observation.tool_name
        for observation in context.observations
        if observation.status in {"ok", "not_found"}
    )
    return frozenset(
        tool for tool in q5_required_state_tools(context) if tool not in observed_tools
    )


def _build_context(
    task: Q5TaskInput,
    pass_result: RetrievalPassResult,
    report: ConditionReport,
    condition_legal_actions: list[GovernanceAction],
    *,
    observations: list[Q5TrustedObservation],
    remaining_observations: int,
    terminal_only: bool = False,
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
        terminal_only=terminal_only,
        remaining_observation_budget=remaining_observations,
        remaining_terminal_budget=1,
    )


def _reject_tool_and_escalate(
    *,
    fallback_cause: Q5FallbackCause,
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
            reason_code=fallback_cause.value,
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
        proposal=_safe_escalation(context, fallback_cause),
        policy_source=policy_source,
        step_index=step_index,
        context_version=context_version,
        fallback_cause=fallback_cause,
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
    fallback_cause: Q5FallbackCause | None = None,
) -> Q5AgentResult:
    terminal_step_index = min(3, max(step_index, len(state.tool_events) + 1))
    effective = proposal
    causal_authorization_reason: str | None = None
    authorized_ids = {item.chunk_id for item in context.authorized_evidence}
    unresolved_tools = q5_unresolved_state_tools(context)
    if not set(proposal.evidence_chunk_ids).issubset(authorized_ids):
        fallback_cause = fallback_cause or Q5FallbackCause.invalid_evidence_citation
        effective = _safe_escalation(context, fallback_cause)
    elif proposal.action not in context.legal_terminal_actions:
        fallback_cause = fallback_cause or Q5FallbackCause.illegal_terminal_action
        effective = _safe_escalation(context, fallback_cause)
    elif proposal.action in _SIDE_EFFECT_ACTIONS and unresolved_tools:
        fallback_cause = (
            fallback_cause or Q5FallbackCause.premature_terminal_unresolved_state
        )
        effective = _safe_escalation(context, fallback_cause)

    authorization = reauthorize_q5_proposal(
        effective,
        actor_claims=task.actor,
        requested_capability=task.requested_capability,
        available_tools=task.available_tools,
    )
    if not authorization.allowed:
        causal_authorization_reason = authorization.reason_code
        fallback_cause = fallback_cause or Q5FallbackCause.reauthorization_rejection
        effective = _safe_escalation(context, fallback_cause)
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
    q4_budget = GovernanceBudget(max_actions=1)
    host_noop_short_circuit = bool(
        effective.action is GovernanceAction.no_op and not proposal_report.conditions
    )
    q4_validation_input = {
        "proposal": q4_proposal.model_dump(mode="json"),
        "report": proposal_report.model_dump(mode="json"),
        "budget": q4_budget.model_dump(mode="json"),
        "host_noop_short_circuit": host_noop_short_circuit,
    }
    if host_noop_short_circuit:
        q4_validation = GovValidationResult(ok=True)
    else:
        q4_validation = validate_governance(
            q4_proposal,
            proposal_report,
            q4_budget,
        )

    if not q4_validation.ok:
        if fallback_cause is None:
            fallback_cause = Q5FallbackCause.q4_rejection
            effective = _safe_escalation(context, fallback_cause)
            authorization = reauthorize_q5_proposal(
                effective,
                actor_claims=task.actor,
                requested_capability=task.requested_capability,
                available_tools=task.available_tools,
            )
            if not authorization.allowed:  # pragma: no cover - universally safe
                raise RuntimeError("Q5 host fallback escalation failed reauthorization")

    assert effective.action is not None
    final_action = effective.action

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
            reason_code=(
                Q5_FALLBACK_TERMINAL_REASON_CODE[fallback_cause]
                if fallback_cause is not None
                else effective.reason_code
            ),
            proposal_kind=Q5ProposalKind.terminal,
            action=final_action,
            policy_disposition=(
                effective.decision_basis.policy_disposition
                if effective.decision_basis is not None
                else None
            ),
            disposition_source=effective.disposition_source,
            authorization_reason=(
                causal_authorization_reason or authorization.reason_code
            ),
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
        q4_validation_input=q4_validation_input,
        record=record,
        tool_events=list(state.tool_events),
        policy_events=list(state.policy_events),
        otel_spans=list(state.spans),
        trajectory=list(state.trajectory),
        context_traces=list(state.context_traces),
        observation_count=len(state.tool_events),
        terminal_proposal_count=1,
        step_count=terminal_step_index,
        llm_calls=state.llm_calls,
        duplicate_successful_observation_count=(state.duplicate_successful_observation_count),
        post_observation_terminal_rate=(
            state.terminal_selected_from_terminal_only / state.terminal_only_prompt_count
            if state.terminal_only_prompt_count
            else None
        ),
        fallback_reason=(
            Q5_FALLBACK_RESULT_REASON[fallback_cause]
            if fallback_cause is not None
            else None
        ),
    )


def _safe_escalation(
    context: Q5DecisionContext,
    fallback_cause: Q5FallbackCause,
) -> Q5StructuredProposal:
    return Q5StructuredProposal(
        kind=Q5ProposalKind.terminal,
        tool=None,
        args={},
        action=GovernanceAction.escalate_to_human,
        decision_basis=None,
        disposition_source="fallback",
        evidence_chunk_ids=[item.chunk_id for item in context.authorized_evidence[:5]],
        reason_code=Q5_FALLBACK_TERMINAL_REASON_CODE[fallback_cause],
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
