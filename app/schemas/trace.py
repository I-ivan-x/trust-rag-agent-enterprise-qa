from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.chat import ChatDecision
from app.schemas.retrieval import RetrievalPlan, RetrievedChunk, UserScope


class TraceStep(BaseModel):
    step_name: str
    status: str = "ok"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latency_ms: float | None = Field(default=None, ge=0)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RetrievalTrace(BaseModel):
    plan: RetrievalPlan | None = None
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GateTrace(BaseModel):
    gate_name: str
    passed: bool
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AgenticRecoveryTrace(BaseModel):
    rewrite_triggered: bool = False
    original_query: str
    rewritten_query: str | None = None
    rewrite_reason: str | None = None
    first_pass_evidence_sufficient: bool | None = None
    second_pass_evidence_sufficient: bool | None = None
    second_pass_attempted: bool = False
    max_rewrite_rounds: int = Field(default=1, ge=0)


class TraceRecord(BaseModel):
    trace_id: str
    session_id: str | None = None
    query: str
    user: UserScope
    workflow_version: str = "week0-skeleton"
    steps: list[TraceStep] = Field(default_factory=list)
    retrieval: RetrievalTrace = Field(default_factory=RetrievalTrace)
    gates: list[GateTrace] = Field(default_factory=list)
    agentic_recovery: AgenticRecoveryTrace
    decision: ChatDecision
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = Field(default=None, ge=0)

