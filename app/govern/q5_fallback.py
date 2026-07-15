"""Closed protocol-v4 fallback taxonomy shared by runtime and verifier."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class Q5FallbackCause(StrEnum):
    policy_parse_error = "policy_parse_error"
    policy_model_error = "policy_model_error"
    invalid_evidence_citation = "invalid_evidence_citation"
    illegal_terminal_action = "illegal_terminal_action"
    premature_terminal_unresolved_state = "premature_terminal_unresolved_state"
    reauthorization_rejection = "reauthorization_rejection"
    observation_reauthorization_rejection = "observation_reauthorization_rejection"
    tool_not_allowed = "tool_not_allowed"
    tool_schema_invalid = "tool_schema_invalid"
    tool_new_entity_injection = "tool_new_entity_injection"
    tool_forbidden_control_field = "tool_forbidden_control_field"
    duplicate_successful_observation = "duplicate_successful_observation"
    terminal_only_observation_rejected = "terminal_only_observation_rejected"
    observation_budget_exhausted = "observation_budget_exhausted"
    step_budget_exhausted = "step_budget_exhausted"
    tool_invalid = "tool_invalid"
    tool_timeout = "tool_timeout"
    q4_rejection = "q4_rejection"
    trusted_rule_policy_block = "trusted_rule_policy_block"


Q5_SYNTHESIZED_FALLBACK_CAUSES: Final[frozenset[Q5FallbackCause]] = frozenset(
    set(Q5FallbackCause) - {Q5FallbackCause.trusted_rule_policy_block}
)

Q5_TOOL_VALIDATION_FALLBACK: Mapping[str, Q5FallbackCause] = MappingProxyType(
    {
        "tool_not_allowed": Q5FallbackCause.tool_not_allowed,
        "schema_invalid": Q5FallbackCause.tool_schema_invalid,
        "new_entity_injection": Q5FallbackCause.tool_new_entity_injection,
        "forbidden_control_field": Q5FallbackCause.tool_forbidden_control_field,
    }
)

Q5_TOOL_REJECTION_REASON_TO_CAUSE: Mapping[str, Q5FallbackCause] = MappingProxyType(
    {
        cause.value: cause
        for cause in (
            Q5FallbackCause.observation_reauthorization_rejection,
            Q5FallbackCause.tool_not_allowed,
            Q5FallbackCause.tool_schema_invalid,
            Q5FallbackCause.tool_new_entity_injection,
            Q5FallbackCause.tool_forbidden_control_field,
            Q5FallbackCause.duplicate_successful_observation,
            Q5FallbackCause.terminal_only_observation_rejected,
            Q5FallbackCause.observation_budget_exhausted,
            Q5FallbackCause.step_budget_exhausted,
        )
    }
)

Q5_FALLBACK_TERMINAL_REASON_CODE: Mapping[Q5FallbackCause, str] = MappingProxyType(
    {
        cause: (
            "policy_block"
            if cause is Q5FallbackCause.trusted_rule_policy_block
            else cause.value
        )
        for cause in Q5FallbackCause
    }
)

Q5_FALLBACK_RESULT_REASON: Mapping[Q5FallbackCause, str | None] = MappingProxyType(
    {
        cause: (
            None
            if cause is Q5FallbackCause.trusted_rule_policy_block
            else cause.value
        )
        for cause in Q5FallbackCause
    }
)
