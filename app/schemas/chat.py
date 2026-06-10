from pydantic import BaseModel, Field, field_validator

from app.core.enums import DecisionReason, ExpectedBehavior
from app.schemas.citation import Citation
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk, UserScope


class ChatRequest(BaseModel):
    query: str
    user: UserScope
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)
    session_id: str | None = None

    @field_validator("query")
    @classmethod
    def _query_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("query must not be blank")
        return value


class ChatDecision(BaseModel):
    refused: bool = False
    reason: DecisionReason = DecisionReason.none
    warnings: list[str] = Field(default_factory=list)
    evidence_sufficient: bool = True
    acl_passed: bool = True
    state_policy: str | None = None
    rewrite_triggered: bool = False
    response_mode: ExpectedBehavior = ExpectedBehavior.answer


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    decision: ChatDecision
    trace_id: str
    retrieved_chunks_preview: list[RetrievedChunk] = Field(default_factory=list)

