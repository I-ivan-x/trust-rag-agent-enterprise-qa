from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import AccessLevel, RetrievalSource
from app.schemas.chunk import Chunk


class UserScope(BaseModel):
    user_id: str
    role: str
    department: str | None = None
    clearance: AccessLevel = AccessLevel.internal


class RetrievalOptions(BaseModel):
    top_k_dense: int = Field(default=20, ge=0)
    top_k_sparse: int = Field(default=20, ge=0)
    top_n_rerank: int = Field(default=8, ge=0)
    return_trace: bool = True
    return_retrieved_chunks: bool = False
    enable_agentic_recovery: bool = True
    max_rewrite_rounds: int = Field(default=1, ge=0)


class RetrievalPlan(BaseModel):
    use_vector: bool = True
    use_keyword: bool = True
    use_reranker: bool = True
    top_k_dense: int = Field(default=20, ge=0)
    top_k_sparse: int = Field(default=20, ge=0)
    top_n_rerank: int = Field(default=8, ge=0)
    filters: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk: Chunk
    source: RetrievalSource
    vector_score: float | None = None
    keyword_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    rank: int = Field(ge=1)


class ContextPack(BaseModel):
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    context_text: str = ""
    token_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)

