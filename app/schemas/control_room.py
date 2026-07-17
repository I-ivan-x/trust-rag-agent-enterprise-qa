"""Strict public schema for the verified control-room trajectory snapshot."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ControlRoomProvenance(_StrictModel):
    source_path: Literal["frontend/src/data/trajectories.json"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: Literal["q4-p5-selection-calibrated"]
    execution_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifact_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    mode: Literal["real"]


class ControlRoomObservation(_StrictModel):
    retrieved: int = Field(ge=0)
    surviving: int = Field(ge=0)
    blocked: int = Field(ge=0)
    citations: list[str] = Field(max_length=3)

    @model_validator(mode="after")
    def _counts_are_possible(self) -> ControlRoomObservation:
        if self.surviving > self.retrieved or self.blocked > self.retrieved:
            raise ValueError("control-room observation counts exceed retrieved chunks")
        return self


class ControlRoomEvidence(_StrictModel):
    conditions: list[str]
    authorized_actor: bool
    evidence_decision: Literal["sufficient", "insufficient"]


class ControlRoomProposal(_StrictModel):
    action: Literal[
        "flag_stale",
        "open_remediation_ticket",
        "send_alert",
        "escalate_to_human",
        "no_op",
    ]
    controller_source: Literal["rule", "llm"]
    risk_tier: Literal["auto", "approval", "terminal", "none"]


class ControlRoomPolicy(_StrictModel):
    validator_ok: bool
    forced_action: str | None


class ControlRoomTerminal(_StrictModel):
    approval_state: Literal["committed", "pending_approval", "escalated", "none"]
    executed_side_effect: bool
    sink_record_id: str | None


class ControlRoomScenario(_StrictModel):
    scenario_id: Literal["approval_path", "blocked_path"]
    source_ref: Literal["ora-t05", "ora-t15"]
    query: str = Field(min_length=1, max_length=300)
    actor_role: Literal["admin", "viewer"]
    authorized: bool
    observation: ControlRoomObservation
    evidence: ControlRoomEvidence
    proposal: ControlRoomProposal
    policy: ControlRoomPolicy
    terminal: ControlRoomTerminal

    @model_validator(mode="after")
    def _authorization_is_consistent(self) -> ControlRoomScenario:
        if self.authorized != self.evidence.authorized_actor:
            raise ValueError("control-room authorization fields disagree")
        if not self.authorized:
            if self.proposal.action != "escalate_to_human":
                raise ValueError("unauthorized scenario must terminate by escalation")
            if self.terminal.executed_side_effect:
                raise ValueError("unauthorized scenario cannot execute a side effect")
        return self


class ControlRoomSnapshot(_StrictModel):
    schema_version: Literal["control-room-trajectory-v1"]
    provenance: ControlRoomProvenance
    scenarios: list[ControlRoomScenario] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _scenario_set_is_complete(self) -> ControlRoomSnapshot:
        expected = {("approval_path", "ora-t05"), ("blocked_path", "ora-t15")}
        actual = {(row.scenario_id, row.source_ref) for row in self.scenarios}
        if actual != expected:
            raise ValueError("control-room scenario set is incomplete or duplicated")
        return self
