"""Frozen deterministic observation policy for the Q5 rule-agent baseline."""

from __future__ import annotations

import re

from app.govern.conditions import GovernanceAction, OpsCondition
from app.govern.q5_context import (
    Q5_ACTION_TO_DISPOSITION,
    Q5DecisionBasis,
    Q5DecisionContext,
    Q5ProposalKind,
    Q5StructuredProposal,
    Q5TrustedObservation,
)
from app.govern.q5_policy import Q5PolicyStep
from app.schemas.q5_task import Q5ObservationTool

_REFERENCE_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*:[a-z0-9_./:-]+", re.IGNORECASE)


class Q5RuleAgentPolicy:
    policy_source = "rule"

    def decide(self, context: Q5DecisionContext) -> Q5PolicyStep:
        proposal = self._proposal(context)
        return Q5PolicyStep(
            proposal=proposal,
            policy_source="rule",
            parse_status="accepted",
            llm_called=False,
        )

    def _proposal(self, context: Q5DecisionContext) -> Q5StructuredProposal:
        return q5_fixed_table_runtime_proposal(context)


def q5_fixed_table_runtime_proposal(
    context: Q5DecisionContext,
) -> Q5StructuredProposal:
    """Apply the audited three-family table to runtime-visible state only."""

    if (
        OpsCondition.permission_blocked in context.conditions
        or OpsCondition.insufficient_evidence in context.conditions
        or context.evidence_decision == "insufficient"
    ):
        return _policy_block_terminal(context)

    references = _references(context)
    if any(
        condition in context.conditions
        for condition in (OpsCondition.config_violation, OpsCondition.policy_violation)
    ):
        tool = Q5ObservationTool.lookup_policy_exception
        observation = _last_observation(context, tool)
        if observation is None and _can_observe(context, tool):
            resource_ref = _first_prefixed(references, "resource:")
            policy_ref = _first_prefixed(references, "policy:")
            if resource_ref and policy_ref:
                return _observe(
                    context,
                    tool,
                    {"resource_ref": resource_ref, "policy_ref": policy_ref},
                    "lookup_policy_exception",
                )
        if observation is not None:
            status = _observation_status(observation)
            requested_scope = _requested_scope(context.query)
            observed_scope = _observation_scope(observation)
            active_scope_matches = bool(
                status == "active"
                and (
                    requested_scope is None
                    or observed_scope is None
                    or requested_scope == observed_scope
                )
            )
            action = (
                GovernanceAction.escalate_to_human
                if active_scope_matches
                else GovernanceAction.open_remediation_ticket
            )
            return _terminal(context, action, "policy_state_applied")

    if any(
        condition in context.conditions
        for condition in (OpsCondition.stale_procedure, OpsCondition.missing_prereq)
    ):
        tool = Q5ObservationTool.inspect_change_state
        observation = _last_observation(context, tool)
        if observation is None and _can_observe(context, tool):
            change_ref = _first_prefixed(references, "change:")
            if change_ref:
                return _observe(
                    context,
                    tool,
                    {"change_ref": change_ref},
                    "inspect_change_state",
                )
        if observation is not None:
            status = _observation_status(observation)
            if status in {"planned", "unknown"}:
                return _terminal(
                    context,
                    GovernanceAction.escalate_to_human,
                    "change_state_needs_review",
                )
            action = (
                GovernanceAction.flag_stale
                if OpsCondition.stale_procedure in context.conditions
                else GovernanceAction.open_remediation_ticket
            )
            return _terminal(context, action, "change_state_applied")

    if OpsCondition.active_active_conflict in context.conditions:
        tool = Q5ObservationTool.inspect_incident_impact
        observation = _last_observation(context, tool)
        if observation is None and _can_observe(context, tool):
            resource_ref = _first_prefixed(references, "resource:")
            if resource_ref:
                return _observe(
                    context,
                    tool,
                    {"resource_ref": resource_ref},
                    "inspect_incident_impact",
                )
        if observation is not None:
            impacted = _observation_status(observation) in {
                "degraded",
                "outage",
            }
            non_production = _requested_scope(context.query) in {
                "development",
                "sandbox",
                "staging",
            }
            action = (
                GovernanceAction.send_alert
                if impacted and not non_production
                else GovernanceAction.escalate_to_human
            )
            return _terminal(context, action, "incident_state_applied")

    return _terminal(context, _default_action(context), "deterministic_mapping")


def _can_observe(context: Q5DecisionContext, tool: Q5ObservationTool) -> bool:
    return context.remaining_observation_budget > 0 and tool in context.available_tools


def _last_observation(
    context: Q5DecisionContext,
    tool: Q5ObservationTool,
) -> Q5TrustedObservation | None:
    for observation in reversed(context.observations):
        if observation.tool_name is tool:
            return observation
    return None


def _observation_status(observation: Q5TrustedObservation) -> str:
    if observation.status in {"timeout", "invalid"}:
        return observation.status
    if not observation.observation:
        return "unknown"
    return str(observation.observation.get("status", "unknown"))


def _observation_scope(observation: Q5TrustedObservation) -> str | None:
    if not observation.observation:
        return None
    scope = observation.observation.get("scope")
    return str(scope).lower() if isinstance(scope, str) and scope else None


def _requested_scope(query: str) -> str | None:
    lowered = query.lower()
    for scope in ("production", "staging", "sandbox", "development"):
        if re.search(rf"\b{scope}\b", lowered):
            return scope
    return None


def _references(context: Q5DecisionContext) -> list[str]:
    references = list(context.resource_refs)
    for evidence in context.authorized_evidence:
        references.extend(_REFERENCE_PATTERN.findall(evidence.text_excerpt))
        if evidence.relation_summary:
            references.extend(_REFERENCE_PATTERN.findall(evidence.relation_summary))
    for observation in context.observations:
        if observation.observation:
            references.extend(_nested_reference_values(observation.observation))
    return list(dict.fromkeys(references))


def _nested_reference_values(value) -> list[str]:
    if isinstance(value, str):
        return [value] if _REFERENCE_PATTERN.fullmatch(value) else []
    if isinstance(value, dict):
        out: list[str] = []
        for nested in value.values():
            out.extend(_nested_reference_values(nested))
        return out
    if isinstance(value, list):
        out = []
        for nested in value:
            out.extend(_nested_reference_values(nested))
        return out
    return []


def _first_prefixed(references: list[str], prefix: str) -> str | None:
    return next((value for value in references if value.startswith(prefix)), None)


def _default_action(context: Q5DecisionContext) -> GovernanceAction:
    if OpsCondition.stale_procedure in context.conditions:
        return GovernanceAction.flag_stale
    if any(
        condition in context.conditions
        for condition in (
            OpsCondition.config_violation,
            OpsCondition.policy_violation,
            OpsCondition.missing_prereq,
            OpsCondition.broken_xref,
        )
    ):
        return GovernanceAction.open_remediation_ticket
    if OpsCondition.active_active_conflict in context.conditions:
        return GovernanceAction.send_alert
    if context.conditions:
        return GovernanceAction.escalate_to_human
    return GovernanceAction.no_op


def _observe(
    context: Q5DecisionContext,
    tool: Q5ObservationTool,
    args: dict[str, str],
    reason_code: str,
) -> Q5StructuredProposal:
    return Q5StructuredProposal(
        kind=Q5ProposalKind.observe,
        tool=tool,
        args=args,
        action=None,
        evidence_chunk_ids=[item.chunk_id for item in context.authorized_evidence[:5]],
        reason_code=reason_code,
        reason_summary="A trusted read-only observation is required before terminal action.",
    )


def _terminal(
    context: Q5DecisionContext,
    action: GovernanceAction,
    reason_code: str,
) -> Q5StructuredProposal:
    if action not in context.legal_terminal_actions:
        if GovernanceAction.escalate_to_human in context.legal_terminal_actions:
            action = GovernanceAction.escalate_to_human
            reason_code = "legal_action_fallback"
        elif GovernanceAction.no_op in context.legal_terminal_actions:
            action = GovernanceAction.no_op
            reason_code = "legal_noop_fallback"
    evidence_ids = [item.chunk_id for item in context.authorized_evidence[:5]]
    successful_request = next(
        (
            item.request_id
            for item in reversed(context.observations)
            if item.status in {"ok", "not_found"}
        ),
        None,
    )
    grounded = bool(evidence_ids) and (not context.terminal_only or successful_request)
    return Q5StructuredProposal(
        kind=Q5ProposalKind.terminal,
        tool=None,
        args={},
        action=action,
        decision_basis=(
            Q5DecisionBasis(
                policy_disposition=Q5_ACTION_TO_DISPOSITION[action],
                evidence_chunk_id=evidence_ids[0],
                observation_request_id=successful_request,
            )
            if grounded
            else None
        ),
        disposition_source="rule" if grounded else "fallback",
        evidence_chunk_ids=evidence_ids,
        reason_code=reason_code,
        reason_summary="The deterministic policy selected a terminal governance action.",
    )


def _policy_block_terminal(context: Q5DecisionContext) -> Q5StructuredProposal:
    """Emit the host-audited terminal form reserved for a real policy block."""

    return Q5StructuredProposal(
        kind=Q5ProposalKind.terminal,
        tool=None,
        args={},
        action=GovernanceAction.escalate_to_human,
        decision_basis=None,
        disposition_source="fallback",
        evidence_chunk_ids=[item.chunk_id for item in context.authorized_evidence[:5]],
        reason_code="policy_block",
        reason_summary="Runtime policy requires safe escalation without a model decision.",
    )
