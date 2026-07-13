"""Frozen compatibility contracts for sealed Q5 protocol-v3 artifacts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.eval import q5_metrics_v3
from app.eval.q5_report_v3 import render_q5_report as _render_q5_report_v3
from app.govern.conditions import GovernanceAction
from app.govern.q5_context import Q5ProposalKind, assert_q5_no_gold_or_control_fields
from app.schemas.q5_task import Q5ObservationTool


class Q5StructuredProposalV3(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Q5ProposalKind
    tool: Q5ObservationTool | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    action: GovernanceAction | None = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    reason_summary: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def _validate_v3_shape(self) -> Q5StructuredProposalV3:
        assert_q5_no_gold_or_control_fields(self.args)
        if self.kind is Q5ProposalKind.observe:
            if self.tool is None or self.action is not None or not self.args:
                raise ValueError("invalid v3 observe proposal")
        elif self.tool is not None or self.action is None or self.args:
            raise ValueError("invalid v3 terminal proposal")
        if "\n" in self.reason_summary or "\r" in self.reason_summary:
            raise ValueError("reason_summary must be one line")
        if self.reason_code == "short_enum":
            raise ValueError("reason_code must be concrete")
        if len(self.evidence_chunk_ids) != len(set(self.evidence_chunk_ids)):
            raise ValueError("evidence_chunk_ids must be unique")
        return self


class Q5PolicyDecisionEventV3(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["q5_policy_decision"] = "q5_policy_decision"
    step_index: int = Field(ge=1, le=3)
    context_version: int = Field(ge=1)
    policy_source: Literal["rule", "llm"]
    parse_status: Literal["accepted", "parse_error", "model_error"]
    error_reason: str | None = Field(default=None, max_length=128)
    raw_payload_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    accepted_proposal: Q5StructuredProposalV3 | None = None
    llm_called: bool = False

    @model_validator(mode="after")
    def _validate_v3_event(self) -> Q5PolicyDecisionEventV3:
        if self.parse_status == "accepted":
            if self.accepted_proposal is None or self.error_reason is not None:
                raise ValueError("invalid accepted v3 event")
        elif self.accepted_proposal is not None or not self.error_reason:
            raise ValueError("invalid failed v3 event")
        if self.error_reason and ("\n" in self.error_reason or "\r" in self.error_reason):
            raise ValueError("error_reason must be one line")
        if self.parse_status == "parse_error" and self.raw_payload_sha256 is None:
            raise ValueError("parse error requires raw hash")
        if (
            self.policy_source == "llm"
            and self.llm_called
            and self.parse_status == "accepted"
            and self.raw_payload_sha256 is None
        ):
            raise ValueError("accepted LLM event requires raw hash")
        if self.policy_source == "rule" and self.llm_called:
            raise ValueError("rule event cannot call LLM")
        return self


def compute_q5_metrics_v3(
    rows: list[dict[str, Any]], *, k: int, seed: int, bootstrap_resamples: int
) -> dict[str, Any]:
    return q5_metrics_v3.compute_q5_metrics(
        rows, k=k, seed=seed, bootstrap_resamples=bootstrap_resamples
    )


def evaluate_q5_gates_v3(summary: dict[str, Any]) -> dict[str, Any]:
    return q5_metrics_v3.evaluate_q5_gates(summary)


def render_q5_report_v3(summary: dict[str, Any], gates: dict[str, Any]) -> str:
    return _render_q5_report_v3(summary, gates)
