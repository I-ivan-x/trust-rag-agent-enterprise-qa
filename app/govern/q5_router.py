"""Deterministic Q5 selective router over runtime-only facts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.govern.conditions import GovernanceAction


class Q5MissingStateType(StrEnum):
    policy_exception = "policy_exception"
    change_state = "change_state"
    incident_impact = "incident_impact"


class Q5RouteReason(StrEnum):
    rule_baseline = "rule_baseline"
    always_llm_control = "always_llm_control"
    terminal_policy_block = "terminal_policy_block"
    trusted_state_complete = "trusted_state_complete"
    missing_trusted_state = "missing_trusted_state"
    multiple_plausible_outcomes = "multiple_plausible_outcomes"
    deterministic_fallback = "deterministic_fallback"


class Q5RouteFacts(BaseModel):
    """No grader fields are accepted; extra=strict blocks stratum/gold injection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    terminal_policy_block: bool = False
    structured_state_complete: bool = False
    observable_ambiguity_count: int = Field(default=0, ge=0)
    missing_state_types: list[Q5MissingStateType] = Field(default_factory=list)
    candidate_terminal_actions: list[GovernanceAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_runtime_facts(self) -> Q5RouteFacts:
        if self.structured_state_complete and self.missing_state_types:
            raise ValueError("structured state cannot be complete while state is missing")
        return self


class Q5RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Literal["rule", "llm"]
    route_reasons: list[Q5RouteReason]
    observable_ambiguity_count: int = Field(ge=0)
    missing_state_types: list[Q5MissingStateType]
    candidate_terminal_actions: list[GovernanceAction]


def route_q5(facts: Q5RouteFacts) -> Q5RouteDecision:
    if facts.terminal_policy_block:
        route = "rule"
        reasons = [Q5RouteReason.terminal_policy_block]
    elif facts.structured_state_complete:
        route = "rule"
        reasons = [Q5RouteReason.trusted_state_complete]
    elif facts.missing_state_types or facts.observable_ambiguity_count > 0:
        route = "llm"
        reasons = [Q5RouteReason.missing_trusted_state]
        if facts.observable_ambiguity_count > 1:
            reasons.append(Q5RouteReason.multiple_plausible_outcomes)
    else:
        route = "rule"
        reasons = [Q5RouteReason.deterministic_fallback]
    return Q5RouteDecision(
        route=route,
        route_reasons=reasons,
        observable_ambiguity_count=facts.observable_ambiguity_count,
        missing_state_types=list(facts.missing_state_types),
        candidate_terminal_actions=list(facts.candidate_terminal_actions),
    )
