from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.enums import DecisionReason, ExpectedBehavior
from app.schemas.citation import Citation
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk, UserScope


class ChatRequest(BaseModel):
    query: str
    user: UserScope
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)
    session_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_week3_flat_request(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "options" not in normalized and "retrieval_options" in normalized:
            normalized["options"] = normalized["retrieval_options"]
        if "user" not in normalized and "user_role" in normalized:
            normalized["user"] = {
                "user_id": normalized.get("user_id", "anonymous-local-user"),
                "role": normalized["user_role"],
                "department": normalized.get("user_department"),
                "clearance": normalized.get("user_clearance", "internal"),
            }
        return normalized

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
    response_mode: ExpectedBehavior = ExpectedBehavior.answer
    trace_id: str
    retrieved_chunks_preview: list[RetrievedChunk] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
