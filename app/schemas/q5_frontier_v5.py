"""Closed contracts preregistered for the K0T development frontier."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.q5_frontier import FrontierDisposition
from app.schemas.q5_frontier_v2 import FrontierTrustedObservation


class FrontierRuntimePayloadV5(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_ref: str = Field(pattern=r"^frontier-k0t-dev-resource:r[0-9]{3}$")
    policy_text: str = Field(min_length=1)
    query: str = Field(min_length=1)
    legal_dispositions: list[FrontierDisposition] = Field(min_length=1)
    trusted_observation: FrontierTrustedObservation

    @model_validator(mode="after")
    def _legal_surface(self) -> FrontierRuntimePayloadV5:
        if len(self.legal_dispositions) != len(set(self.legal_dispositions)):
            raise ValueError("legal dispositions must be unique")
        if FrontierDisposition.human_review not in self.legal_dispositions:
            raise ValueError("human_review must remain legal")
        return self


class K0TAttackResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[
        "family_only",
        "phenomenon_only",
        "renderer_template_only",
        "token_pattern_state_equality",
        "action_phrase_omitted",
        "lexical_condition_action_parser",
        "majority_action",
        "pair_neighbor",
    ]
    evaluated_count: int = Field(ge=1)
    success_count: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    breached: bool


class K0TAttackAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-k0t-shortcut-audit-v1"] = "q5-k0t-shortcut-audit-v1"
    semantic_case_count: int = Field(ge=1)
    attacks: list[K0TAttackResult] = Field(min_length=8, max_length=8)
    headroom_survives: bool
    external_requests: Literal[0] = 0
    model_requests: Literal[0] = 0

    @model_validator(mode="after")
    def _closure(self) -> K0TAttackAudit:
        if len({item.name for item in self.attacks}) != 8:
            raise ValueError("all eight unique shortcut attacks are required")
        if self.headroom_survives == any(item.breached for item in self.attacks):
            raise ValueError("headroom result disagrees with shortcut breaches")
        return self
