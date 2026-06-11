from __future__ import annotations

from app.context.context_assembler import ContextPack, assemble_context
from app.core.enums import AccessLevel, DocumentStatus, RetrievalSource
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


def test_assemble_context_orders_by_rerank_and_deduplicates() -> None:
    chunks = [
        _retrieved("chunk-a", "alpha text", 1, 0.2),
        _retrieved("chunk-b", "beta text", 2, 0.9),
        _retrieved("chunk-b", "duplicate beta", 3, 0.8),
    ]

    context = assemble_context("query", chunks, token_budget=20, max_chunks=5)

    assert [chunk.chunk_id for chunk in context.chunks] == ["chunk-b", "chunk-a"]
    assert any("Duplicate chunk skipped" in warning for warning in context.warnings)


def test_assemble_context_respects_token_budget_without_partial_text() -> None:
    chunks = [
        _retrieved("chunk-a", "one two", 1, 0.9),
        _retrieved("chunk-b", "three four five six", 2, 0.8),
    ]

    context = assemble_context("query", chunks, token_budget=3, max_chunks=5)

    assert [chunk.chunk_id for chunk in context.chunks] == ["chunk-a"]
    assert context.chunks[0].text == "one two"
    assert any("Context token budget reached" in warning for warning in context.warnings)


def test_assemble_context_preserves_metadata_and_round_trips_json() -> None:
    result = _retrieved("chunk-a", "restricted deprecated text", 1, 0.9)
    result.chunk.status = DocumentStatus.deprecated
    result.chunk.access_level = AccessLevel.restricted
    result.chunk.allowed_roles = ["admin"]

    context = assemble_context("query", [result], token_budget=20, max_chunks=5)
    round_trip = ContextPack.model_validate_json(context.model_dump_json())

    assert round_trip == context
    assert round_trip.chunks[0].status == DocumentStatus.deprecated
    assert round_trip.chunks[0].access_level == AccessLevel.restricted
    assert round_trip.chunks[0].allowed_roles == ["admin"]
    assert round_trip.chunks[0].line_start == 10
    assert round_trip.chunks[0].rerank_score == 0.9


def _retrieved(
    chunk_id: str,
    text: str,
    rank: int,
    rerank_score: float,
) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        doc_id="doc-test",
        chunk_index=rank - 1,
        text=text,
        section_path=["Doc", "Section"],
        token_count=len(text.split()),
        char_count=len(text),
        line_start=10,
        line_end=12,
        status=DocumentStatus.active,
        version="v1",
        allowed_roles=["employee"],
        access_level=AccessLevel.internal,
    )
    return RetrievedChunk(
        chunk=chunk,
        source=RetrievalSource.rerank,
        rrf_score=0.4,
        rerank_score=rerank_score,
        rank=rank,
    )
