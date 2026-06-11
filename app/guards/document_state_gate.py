from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import DocumentStatus
from app.schemas.retrieval import RetrievedChunk


class StateGateDecision(BaseModel):
    surviving_chunks: list[RetrievedChunk] = Field(default_factory=list)
    deprecated_chunks: list[RetrievedChunk] = Field(default_factory=list)
    blocked_chunks: list[RetrievedChunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def apply_document_state_gate(chunks: list[RetrievedChunk]) -> StateGateDecision:
    surviving_chunks: list[RetrievedChunk] = []
    deprecated_chunks: list[RetrievedChunk] = []
    blocked_chunks: list[RetrievedChunk] = []
    warnings: list[str] = []

    for chunk in chunks:
        status = chunk.chunk.status
        if status == DocumentStatus.active:
            surviving_chunks.append(chunk)
        elif status == DocumentStatus.deprecated:
            deprecated_chunks.append(chunk)
            warnings.append(
                f"Deprecated evidence withheld from normal answer: {chunk.chunk.chunk_id}"
            )
        elif status in {DocumentStatus.archived, DocumentStatus.draft}:
            blocked_chunks.append(chunk)
            warnings.append(
                f"Document state blocked chunk {chunk.chunk.chunk_id}: status={status.value}"
            )
        else:
            blocked_chunks.append(chunk)
            warnings.append(
                f"Unknown document state blocked chunk {chunk.chunk.chunk_id}: status={status}"
            )

    return StateGateDecision(
        surviving_chunks=surviving_chunks,
        deprecated_chunks=deprecated_chunks,
        blocked_chunks=blocked_chunks,
        warnings=warnings,
    )
