from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.core.enums import AccessLevel, CorpusSource, DocumentStatus, MetadataOrigin
from app.schemas.retrieval import RetrievedChunk

_TOKEN_PATTERN = re.compile(r"\S+")


class ContextChunk(BaseModel):
    chunk_id: str
    doc_id: str
    section_path: list[str] = Field(default_factory=list)
    text: str
    status: DocumentStatus
    access_level: AccessLevel
    allowed_roles: list[str] = Field(default_factory=list)
    corpus_source: CorpusSource
    metadata_origin: MetadataOrigin
    line_start: int | None = None
    line_end: int | None = None
    rerank_score: float | None = None
    rrf_score: float | None = None
    vector_score: float | None = None
    keyword_score: float | None = None
    rank: int = Field(ge=1)


class ContextPack(BaseModel):
    query: str
    chunks: list[ContextChunk] = Field(default_factory=list)
    token_budget: int = Field(default=1800, ge=0)
    estimated_tokens: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)

    @property
    def context_text(self) -> str:
        return "\n\n".join(
            f"[{chunk.chunk_id}]\n{chunk.text}" for chunk in self.chunks
        )


def assemble_context(
    query: str,
    reranked_chunks: list[RetrievedChunk],
    token_budget: int = 1800,
    max_chunks: int = 6,
) -> ContextPack:
    warnings: list[str] = []
    if token_budget < 0:
        raise ValueError("token_budget must be non-negative")
    if max_chunks < 0:
        raise ValueError("max_chunks must be non-negative")
    if token_budget == 0 or max_chunks == 0:
        return ContextPack(
            query=query,
            chunks=[],
            token_budget=token_budget,
            estimated_tokens=0,
            warnings=["Context budget or max_chunks is zero."],
        )

    sorted_chunks = sorted(
        reranked_chunks,
        key=lambda item: (
            -(item.rerank_score if item.rerank_score is not None else float("-inf")),
            -(item.rrf_score if item.rrf_score is not None else 0.0),
            item.rank,
            item.chunk.chunk_id,
        ),
    )

    seen_chunk_ids: set[str] = set()
    selected: list[ContextChunk] = []
    estimated_tokens = 0
    for result in sorted_chunks:
        chunk = result.chunk
        if chunk.chunk_id in seen_chunk_ids:
            warnings.append(f"Duplicate chunk skipped: {chunk.chunk_id}")
            continue
        seen_chunk_ids.add(chunk.chunk_id)

        chunk_tokens = _estimate_tokens(chunk.text)
        if estimated_tokens + chunk_tokens > token_budget:
            warnings.append(
                "Context token budget reached; remaining chunks were omitted without "
                f"partial-sentence truncation. skipped_chunk_id={chunk.chunk_id}"
            )
            continue
        selected.append(
            ContextChunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                section_path=chunk.section_path,
                text=chunk.text,
                status=chunk.status,
                access_level=chunk.access_level,
                allowed_roles=chunk.allowed_roles,
                corpus_source=chunk.corpus_source,
                metadata_origin=chunk.metadata_origin,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                rerank_score=result.rerank_score,
                rrf_score=result.rrf_score,
                vector_score=result.vector_score,
                keyword_score=result.keyword_score,
                rank=len(selected) + 1,
            )
        )
        estimated_tokens += chunk_tokens
        if len(selected) >= max_chunks:
            break

    return ContextPack(
        query=query,
        chunks=selected,
        token_budget=token_budget,
        estimated_tokens=estimated_tokens,
        warnings=warnings,
    )


def _estimate_tokens(text: str) -> int:
    return max(1, len(_TOKEN_PATTERN.findall(text)))
