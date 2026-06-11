from __future__ import annotations

from pydantic import BaseModel, Field

from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.schemas.retrieval import RetrievedChunk


class RetrievalPassResult(BaseModel):
    query: str
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    reranked_chunks: list[RetrievedChunk] = Field(default_factory=list)
    state_decision: StateGateDecision
    acl_decision: ACLGateDecision
    conflict_decision: ConflictDecision
    evidence_decision: EvidenceGateDecision
    warnings: list[str] = Field(default_factory=list)


class AgenticRecoveryState(BaseModel):
    original_query: str
    rewritten_query: str | None = None
    rewrite_triggered: bool = False
    rewrite_reason: str | None = None
    first_pass_evidence_sufficient: bool | None = None
    second_pass_evidence_sufficient: bool | None = None
    second_pass_attempted: bool = False
    retrieval_pass_count: int = Field(default=1, ge=1)
    max_rewrite_rounds: int = Field(default=1, ge=0)
