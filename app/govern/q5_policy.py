"""Shared typed contracts for Q5 rule and LLM policies."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.govern.q5_context import Q5DecisionContext, Q5StructuredProposal


class Q5PolicyModel(Protocol):
    def generate(self, prompt: str) -> str: ...


class Q5PolicyStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal: Q5StructuredProposal | None = None
    policy_source: Literal["rule", "llm"]
    parse_status: Literal["accepted", "parse_error", "model_error"]
    error_reason: str | None = None
    raw_payload_sha256: str | None = None
    llm_called: bool = False

    @model_validator(mode="after")
    def _validate_policy_step(self) -> Q5PolicyStep:
        _validate_policy_decision_fields(
            parse_status=self.parse_status,
            proposal=self.proposal,
            error_reason=self.error_reason,
            raw_payload_sha256=self.raw_payload_sha256,
            policy_source=self.policy_source,
            llm_called=self.llm_called,
        )
        return self


class Q5PolicyDecisionEvent(BaseModel):
    """Auditable policy decision without retaining raw model output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["q5_policy_decision"] = "q5_policy_decision"
    step_index: int = Field(ge=1, le=3)
    context_version: int = Field(ge=1)
    policy_source: Literal["rule", "llm"]
    parse_status: Literal["accepted", "parse_error", "model_error"]
    error_reason: str | None = Field(default=None, max_length=128)
    raw_payload_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    accepted_proposal: Q5StructuredProposal | None = None
    llm_called: bool = False

    @model_validator(mode="after")
    def _validate_policy_event(self) -> Q5PolicyDecisionEvent:
        _validate_policy_decision_fields(
            parse_status=self.parse_status,
            proposal=self.accepted_proposal,
            error_reason=self.error_reason,
            raw_payload_sha256=self.raw_payload_sha256,
            policy_source=self.policy_source,
            llm_called=self.llm_called,
        )
        return self


class Q5AgentPolicy(Protocol):
    policy_source: str

    def decide(self, context: Q5DecisionContext) -> Q5PolicyStep: ...


def _validate_policy_decision_fields(
    *,
    parse_status: Literal["accepted", "parse_error", "model_error"],
    proposal: Q5StructuredProposal | None,
    error_reason: str | None,
    raw_payload_sha256: str | None,
    policy_source: Literal["rule", "llm"],
    llm_called: bool,
) -> None:
    if parse_status == "accepted":
        if proposal is None:
            raise ValueError("accepted policy decision requires a parsed proposal")
        if error_reason is not None:
            raise ValueError("accepted policy decision forbids error_reason")
    else:
        if proposal is not None:
            raise ValueError("failed policy decision forbids accepted proposal")
        if not error_reason:
            raise ValueError("failed policy decision requires error_reason")
    if error_reason and ("\n" in error_reason or "\r" in error_reason):
        raise ValueError("policy error_reason must be one line")
    if parse_status == "parse_error" and raw_payload_sha256 is None:
        raise ValueError("parse_error policy decision requires raw payload hash")
    if policy_source == "llm" and llm_called and parse_status == "accepted":
        if raw_payload_sha256 is None:
            raise ValueError("accepted LLM decision requires raw payload hash")
    if policy_source == "rule" and llm_called:
        raise ValueError("rule policy decision cannot report an LLM call")
