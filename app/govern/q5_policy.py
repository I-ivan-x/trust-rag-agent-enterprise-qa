"""Shared typed contracts for Q5 rule and LLM policies."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

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


class Q5AgentPolicy(Protocol):
    policy_source: str

    def decide(self, context: Q5DecisionContext) -> Q5PolicyStep: ...
