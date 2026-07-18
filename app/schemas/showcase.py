"""Strict schema for the public-safe interview showcase corpus."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ShowcaseFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal[
        "approval",
        "authorization",
        "authorized_current_evidence",
        "authorized_path",
        "blocked_evidence",
        "blocked_path",
        "demonstration_contract",
        "deprecated_evidence",
        "incident_request",
        "tool_contract",
        "trusted_observation",
    ]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ShowcaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["interview-showcase-manifest-v1"]
    corpus_id: Literal["interview-v1"]
    title: str = Field(min_length=1)
    data_mode: Literal["synthetic"]
    use: Literal["demonstration_only"]
    headline_eligible: Literal[False]
    formal_evaluation: Literal[False]
    model_requests: Literal[0]
    external_requests: Literal[0]
    files: dict[str, ShowcaseFile]

    @model_validator(mode="after")
    def _file_contract(self) -> ShowcaseManifest:
        expected = {
            "access-policy.json",
            "approval-policy.json",
            "authorized-trajectory.json",
            "blocked-trajectory.json",
            "current-runbook.md",
            "deprecated-runbook.md",
            "expected-journey.json",
            "incident-ticket.md",
            "live-observation.json",
            "restricted-exception.md",
            "tool-contract.json",
        }
        if set(self.files) != expected:
            raise ValueError("showcase manifest file matrix is incomplete or contains extras")
        return self

