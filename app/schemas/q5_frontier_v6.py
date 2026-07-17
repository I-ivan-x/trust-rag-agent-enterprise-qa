"""Runtime-only contracts for the practical deterministic frontier."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.q5_frontier import FrontierDisposition


class PracticalObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    scope: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    temporal_state: Literal["current", "planned", "completed", "expired"]
    exception_active: bool
    authorized: bool
    successful: bool


class PracticalRuntimeInput(BaseModel):
    """The complete and only input accepted by practical parsers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_text: str = Field(min_length=1)
    observation: PracticalObservationInput
    legal_dispositions: list[FrontierDisposition] = Field(min_length=1)

    @model_validator(mode="after")
    def _legal_surface(self) -> PracticalRuntimeInput:
        if len(self.legal_dispositions) != len(set(self.legal_dispositions)):
            raise ValueError("legal dispositions must be unique")
        if FrontierDisposition.human_review not in self.legal_dispositions:
            raise ValueError("human_review must remain legal")
        return self


class PracticalParserResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["complete", "abstain", "ambiguous", "unsafe"]
    reason: str
    disposition: FrontierDisposition | None = None

    @model_validator(mode="after")
    def _terminal_only_when_complete(self) -> PracticalParserResult:
        if (self.status == "complete") != (self.disposition is not None):
            raise ValueError("only complete parses may emit a disposition")
        return self
