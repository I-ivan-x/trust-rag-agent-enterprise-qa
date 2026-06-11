from __future__ import annotations

from app.core.enums import AccessLevel, DocumentStatus, RetrievalSource
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


def make_retrieved_chunk(
    chunk_id: str,
    text: str,
    *,
    doc_id: str = "doc-test",
    section_path: list[str] | None = None,
    status: DocumentStatus = DocumentStatus.active,
    access_level: AccessLevel = AccessLevel.internal,
    allowed_roles: list[str] | None = None,
    conflict_group_id: str | None = None,
    rerank_score: float | None = 0.9,
    rank: int = 1,
) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        chunk_index=rank - 1,
        text=text,
        section_path=section_path or ["Test Document", "Section"],
        token_count=len(text.split()),
        char_count=len(text),
        line_start=10,
        line_end=12,
        status=status,
        version="v1",
        allowed_roles=allowed_roles or ["employee"],
        access_level=access_level,
        conflict_group_id=conflict_group_id,
    )
    return RetrievedChunk(
        chunk=chunk,
        source=RetrievalSource.rerank,
        rerank_score=rerank_score,
        rrf_score=0.1,
        rank=rank,
    )
