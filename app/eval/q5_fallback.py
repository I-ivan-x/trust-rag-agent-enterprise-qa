"""Pure protocol-v4 fallback-cause derivation from runtime audit ledgers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.govern.conditions import ConditionReport, GovernanceAction, OpsCondition
from app.govern.q5_fallback import (
    Q5_TOOL_REJECTION_REASON_TO_CAUSE,
    Q5FallbackCause,
)
from app.govern.validator import (
    GovernanceBudget,
    GovernanceProposal,
    GovValidationResult,
    validate_governance,
)

_SIDE_EFFECT_ACTIONS = frozenset(
    {
        GovernanceAction.flag_stale.value,
        GovernanceAction.open_remediation_ticket.value,
        GovernanceAction.send_alert.value,
    }
)
_AUTHORIZATION_REJECTIONS = frozenset(
    {
        "capability_action_denied",
        "role_action_denied",
        "tool_not_available",
        "observation_role_denied",
    }
)


class Q5FallbackCausalWitness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cause: Q5FallbackCause
    witness_kind: Literal[
        "policy_error",
        "tool_rejection",
        "tool_failure",
        "terminal_guard",
        "q4_rejection",
        "step_budget",
        "trusted_rule_policy_block",
    ]
    step_index: int = Field(ge=1, le=3)
    detail: str = Field(min_length=1, max_length=128)


def derive_q5_v4_fallback_witness(
    *,
    result: Mapping[str, Any],
    policy_events: Sequence[Mapping[str, Any]],
    tool_events: Sequence[Mapping[str, Any]],
    trajectory: Sequence[Mapping[str, Any]],
    terminal_event: Mapping[str, Any],
) -> Q5FallbackCausalWitness | None:
    """Derive one HR3 cause solely from the supplied runtime audit ledgers."""

    return _derive_q5_v4_fallback_witness(
        result=result,
        policy_events=policy_events,
        tool_events=tool_events,
        trajectory=trajectory,
        terminal_event=terminal_event,
        strict_policy_block=True,
    )


def derive_q5_v4_fallback_witness_legacy(
    *,
    result: Mapping[str, Any],
    policy_events: Sequence[Mapping[str, Any]],
    tool_events: Sequence[Mapping[str, Any]],
    trajectory: Sequence[Mapping[str, Any]],
    terminal_event: Mapping[str, Any],
) -> Q5FallbackCausalWitness | None:
    """Preserve frozen pre-HR3 protocol-v4 fallback verification semantics."""

    return _derive_q5_v4_fallback_witness(
        result=result,
        policy_events=policy_events,
        tool_events=tool_events,
        trajectory=trajectory,
        terminal_event=terminal_event,
        strict_policy_block=False,
    )


def _derive_q5_v4_fallback_witness(
    *,
    result: Mapping[str, Any],
    policy_events: Sequence[Mapping[str, Any]],
    tool_events: Sequence[Mapping[str, Any]],
    trajectory: Sequence[Mapping[str, Any]],
    terminal_event: Mapping[str, Any],
    strict_policy_block: bool,
) -> Q5FallbackCausalWitness | None:
    """Internal feature-dispatched derivation over same-trial runtime ledgers."""

    candidates: list[Q5FallbackCausalWitness] = []
    terminal_trajectory = [
        item for item in trajectory if item.get("event_type") == "terminal"
    ]
    if len(terminal_trajectory) != 1:
        raise ValueError("Q5 v4 fallback derivation requires one terminal trajectory")
    terminal_step = int(terminal_trajectory[0]["step_index"])
    accepted_at_terminal = [
        item
        for item in policy_events
        if item.get("parse_status") == "accepted"
        and int(item["step_index"]) == terminal_step
        and isinstance(item.get("accepted_proposal"), Mapping)
        and item["accepted_proposal"].get("kind") == "terminal"
    ]

    for event in trajectory:
        if event.get("event_type") != "policy_error":
            continue
        policy = _one_policy_at_step(policy_events, int(event["step_index"]))
        parse_status = policy.get("parse_status")
        if parse_status not in {"parse_error", "model_error"}:
            continue
        cause = (
            Q5FallbackCause.policy_model_error
            if parse_status == "model_error"
            else (
                Q5FallbackCause.tool_schema_invalid
                if policy.get("error_reason") == "tool_schema_invalid"
                else Q5FallbackCause.policy_parse_error
            )
        )
        candidates.append(
            Q5FallbackCausalWitness(
                cause=cause,
                witness_kind="policy_error",
                step_index=int(event["step_index"]),
                detail=str(parse_status),
            )
        )

    for event in trajectory:
        if event.get("event_type") != "tool_rejected":
            continue
        cause = Q5_TOOL_REJECTION_REASON_TO_CAUSE.get(str(event.get("reason_code")))
        policy = _one_policy_at_step(policy_events, int(event["step_index"]))
        proposal = policy.get("accepted_proposal")
        if (
            cause is not None
            and policy.get("parse_status") == "accepted"
            and isinstance(proposal, Mapping)
            and proposal.get("kind") == "observe"
        ):
            candidates.append(
                Q5FallbackCausalWitness(
                    cause=cause,
                    witness_kind="tool_rejection",
                    step_index=int(event["step_index"]),
                    detail=str(event.get("authorization_reason") or "validator_rejection"),
                )
            )

    observation_events = [
        item for item in trajectory if item.get("event_type") == "observation"
    ]
    for tool, observation in zip(tool_events, observation_events, strict=False):
        status = str(tool.get("status") or "")
        if (
            status in ({"invalid"} if strict_policy_block else {"invalid", "timeout"})
            and observation.get("tool_status") == status
            and observation.get("tool") == tool.get("tool_name")
        ):
            candidates.append(
                Q5FallbackCausalWitness(
                    cause=(
                        Q5FallbackCause.tool_invalid
                        if status == "invalid"
                        else Q5FallbackCause.tool_timeout
                    ),
                    witness_kind="tool_failure",
                    step_index=int(observation["step_index"]),
                    detail=status,
                )
            )

    terminal_proposal = terminal_event.get("terminal_proposal")
    route = terminal_event.get("route")
    if strict_policy_block:
        policy_block = _strict_policy_block_witness(
            result=result,
            accepted_at_terminal=accepted_at_terminal,
            terminal_proposal=terminal_proposal,
            terminal_trajectory=terminal_trajectory[0],
            terminal_event=terminal_event,
            route=route,
            terminal_step=terminal_step,
        )
        if policy_block is not None:
            candidates.append(policy_block)
    elif isinstance(terminal_proposal, Mapping) and isinstance(route, Mapping):
        trusted = [
            item
            for item in accepted_at_terminal
            if item.get("accepted_proposal") == terminal_proposal
            and item.get("policy_source") == "rule"
            and item.get("llm_called") is False
            and item.get("raw_payload_sha256") is None
            and item["accepted_proposal"].get("disposition_source") == "fallback"
        ]
        if len(trusted) == 1:
            route_reason = next(iter(route.get("route_reasons") or []), "rule_policy_block")
            candidates.append(
                Q5FallbackCausalWitness(
                    cause=Q5FallbackCause.trusted_rule_policy_block,
                    witness_kind="trusted_rule_policy_block",
                    step_index=terminal_step,
                    detail=str(route_reason),
                )
            )

    original_terminal = (
        accepted_at_terminal[0].get("accepted_proposal")
        if len(accepted_at_terminal) == 1
        else None
    )
    if isinstance(original_terminal, Mapping) and original_terminal != terminal_proposal:
        authorized = set(result.get("authorized_evidence_ids") or [])
        cited = set(original_terminal.get("evidence_chunk_ids") or [])
        candidate_actions = set((route or {}).get("candidate_terminal_actions") or [])
        original_action = str(original_terminal.get("action") or "")
        terminal_authorization = str(
            terminal_trajectory[0].get("authorization_reason") or ""
        )
        basis = original_terminal.get("decision_basis")
        request_id = (
            basis.get("observation_request_id")
            if isinstance(basis, Mapping)
            else None
        )
        successful_requests = {
            item.get("request_id")
            for item in tool_events
            if item.get("status") in {"ok", "not_found"}
        }
        if not cited.issubset(authorized):
            candidates.append(
                _terminal_guard(
                    Q5FallbackCause.invalid_evidence_citation,
                    terminal_step,
                    "unauthorized_evidence",
                )
            )
        elif original_action not in candidate_actions:
            candidates.append(
                _terminal_guard(
                    Q5FallbackCause.illegal_terminal_action,
                    terminal_step,
                    "action_outside_route_candidates",
                )
            )
        elif terminal_authorization in _AUTHORIZATION_REJECTIONS:
            candidates.append(
                _terminal_guard(
                    Q5FallbackCause.reauthorization_rejection,
                    terminal_step,
                    terminal_authorization,
                )
            )
        elif (
            original_action in _SIDE_EFFECT_ACTIONS
            and (route or {}).get("missing_state_types")
            and request_id not in successful_requests
        ):
            candidates.append(
                _terminal_guard(
                    Q5FallbackCause.premature_terminal_unresolved_state,
                    terminal_step,
                    "unresolved_route_state",
                )
            )

    q4 = terminal_event.get("q4_validation")
    q4_input = terminal_event.get("q4_validation_input")
    if _q4_rejection_is_recomputable(
        q4=q4,
        q4_input=q4_input,
        result=result,
        original_terminal=original_terminal,
    ):
        candidates.append(
            Q5FallbackCausalWitness(
                cause=Q5FallbackCause.q4_rejection,
                witness_kind="q4_rejection",
                step_index=terminal_step,
                detail=str(q4.get("reject_reason")),
            )
        )

    if (
        not candidates
        and len(policy_events) == 3
        and all(
            item.get("parse_status") == "accepted"
            and isinstance(item.get("accepted_proposal"), Mapping)
            and item["accepted_proposal"].get("kind") == "observe"
            for item in policy_events
        )
    ):
        candidates.append(
            Q5FallbackCausalWitness(
                cause=Q5FallbackCause.step_budget_exhausted,
                witness_kind="step_budget",
                step_index=3,
                detail="three_observe_policy_steps",
            )
        )

    unique = {
        (item.cause, item.witness_kind, item.step_index, item.detail): item
        for item in candidates
    }
    if len(unique) > 1:
        raise ValueError("Q5 v4 trial contains multiple fallback causal witnesses")
    return next(iter(unique.values()), None)


def _strict_policy_block_witness(
    *,
    result: Mapping[str, Any],
    accepted_at_terminal: Sequence[Mapping[str, Any]],
    terminal_proposal: Any,
    terminal_trajectory: Mapping[str, Any],
    terminal_event: Mapping[str, Any],
    route: Any,
    terminal_step: int,
) -> Q5FallbackCausalWitness | None:
    q4_input = terminal_event.get("q4_validation_input")
    report: ConditionReport | None = None
    if isinstance(q4_input, Mapping):
        try:
            report = ConditionReport.model_validate(q4_input.get("report"))
        except (TypeError, ValueError):
            report = None
    runtime_block = bool(
        report is not None
        and (
            OpsCondition.permission_blocked in report.conditions
            or OpsCondition.insufficient_evidence in report.conditions
            or report.evidence_decision == "insufficient"
        )
    )
    route_block = bool(
        isinstance(route, Mapping)
        and route.get("route") == "rule"
        and route.get("route_reasons") == ["terminal_policy_block"]
    )
    proposal_block = bool(
        isinstance(terminal_proposal, Mapping)
        and terminal_proposal.get("reason_code") == "policy_block"
    )
    trajectory_block = terminal_trajectory.get("reason_code") == "policy_block"
    accepted_block = any(
        isinstance(item.get("accepted_proposal"), Mapping)
        and item["accepted_proposal"].get("reason_code") == "policy_block"
        for item in accepted_at_terminal
    )
    if not any((runtime_block, route_block, proposal_block, trajectory_block, accepted_block)):
        return None

    trusted = [
        item
        for item in accepted_at_terminal
        if item.get("accepted_proposal") == terminal_proposal
        and item.get("policy_source") == "rule"
        and item.get("llm_called") is False
        and item.get("raw_payload_sha256") is None
    ]
    proposal_attested = bool(
        isinstance(terminal_proposal, Mapping)
        and terminal_proposal.get("kind") == "terminal"
        and terminal_proposal.get("action") == GovernanceAction.escalate_to_human.value
        and terminal_proposal.get("decision_basis") is None
        and terminal_proposal.get("disposition_source") == "fallback"
        and terminal_proposal.get("reason_code") == "policy_block"
    )
    trajectory_attested = bool(
        terminal_trajectory.get("policy_source") == "rule"
        and terminal_trajectory.get("action") == GovernanceAction.escalate_to_human.value
        and terminal_trajectory.get("policy_disposition") is None
        and terminal_trajectory.get("disposition_source") == "fallback"
        and terminal_trajectory.get("reason_code") == "policy_block"
    )
    result_attested = bool(
        result.get("final_action") == GovernanceAction.escalate_to_human.value
        and result.get("policy_disposition") is None
        and result.get("disposition_source") == "fallback"
        and result.get("decision_basis_evidence_chunk_id") is None
        and result.get("decision_basis_observation_request_id") is None
        and result.get("fallback_reason") is None
    )
    terminal_attested = bool(
        terminal_event.get("final_action") == GovernanceAction.escalate_to_human.value
        and terminal_event.get("fallback_reason") is None
    )
    route_attested = bool(
        route_block
        and isinstance(route, Mapping)
        and route.get("candidate_terminal_actions")
        == [GovernanceAction.escalate_to_human.value]
    )
    report_attested = bool(
        runtime_block
        and report is not None
        and report.evidence_decision == result.get("evidence_decision")
    )
    if not all(
        (
            len(trusted) == 1,
            proposal_attested,
            trajectory_attested,
            result_attested,
            terminal_attested,
            route_attested,
            report_attested,
        )
    ):
        raise ValueError("Q5 v4 trusted policy-block attestation is incomplete")
    return Q5FallbackCausalWitness(
        cause=Q5FallbackCause.trusted_rule_policy_block,
        witness_kind="trusted_rule_policy_block",
        step_index=terminal_step,
        detail="terminal_policy_block",
    )


def _one_policy_at_step(
    policy_events: Sequence[Mapping[str, Any]],
    step_index: int,
) -> Mapping[str, Any]:
    matches = [item for item in policy_events if item.get("step_index") == step_index]
    return matches[0] if len(matches) == 1 else {}


def _terminal_guard(
    cause: Q5FallbackCause,
    step_index: int,
    detail: str,
) -> Q5FallbackCausalWitness:
    return Q5FallbackCausalWitness(
        cause=cause,
        witness_kind="terminal_guard",
        step_index=step_index,
        detail=detail,
    )


def _q4_rejection_is_recomputable(
    *,
    q4: Any,
    q4_input: Any,
    result: Mapping[str, Any],
    original_terminal: Any,
) -> bool:
    if (
        not isinstance(q4, Mapping)
        or q4.get("ok") is not False
        or q4.get("forced_action") != GovernanceAction.escalate_to_human.value
        or not isinstance(original_terminal, Mapping)
    ):
        return False
    return q5_v4_q4_validation_matches(
        q4=q4,
        q4_input=q4_input,
        result=result,
        expected_proposal_action=str(original_terminal.get("action") or ""),
    )


def q5_v4_q4_validation_matches(
    *,
    q4: Any,
    q4_input: Any,
    result: Mapping[str, Any],
    expected_proposal_action: str,
) -> bool:
    """Replay one serialized Q4 validation input and cross-check trial evidence."""

    if not isinstance(q4, Mapping) or not isinstance(q4_input, Mapping):
        return False
    try:
        proposal = GovernanceProposal.model_validate(q4_input.get("proposal"))
        report = ConditionReport.model_validate(q4_input.get("report"))
        budget = GovernanceBudget.model_validate(q4_input.get("budget"))
    except (TypeError, ValueError):
        return False
    if (
        proposal.action.value != expected_proposal_action
        or report.evidence_decision != result.get("evidence_decision")
        or budget.max_actions != 1
        or budget.consumed != 0
    ):
        return False
    if q4_input.get("host_noop_short_circuit") is True:
        if proposal.action is not GovernanceAction.no_op or report.conditions:
            return False
        recomputed = GovValidationResult(ok=True)
    elif q4_input.get("host_noop_short_circuit") is False:
        recomputed = validate_governance(proposal, report, budget)
    else:
        return False
    return recomputed.model_dump(mode="json") == dict(q4)
