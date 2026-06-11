from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from app.core.enums import DocumentStatus
from app.schemas.retrieval import RetrievedChunk


class ConflictDecision(BaseModel):
    has_conflict: bool = False
    conflict_group_id: str | None = None
    conflicting_chunks: list[RetrievedChunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def detect_minimal_conflict(chunks: list[RetrievedChunk]) -> ConflictDecision:
    grouped: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for result in chunks:
        chunk = result.chunk
        if chunk.status != DocumentStatus.active:
            continue
        if not chunk.conflict_group_id:
            continue
        grouped[chunk.conflict_group_id].append(result)

    for group_id, group_chunks in grouped.items():
        doc_ids = {result.chunk.doc_id for result in group_chunks}
        if len(doc_ids) >= 2:
            return ConflictDecision(
                has_conflict=True,
                conflict_group_id=group_id,
                conflicting_chunks=group_chunks,
                warnings=[
                    "Minimal active-active conflict detected for "
                    f"conflict_group_id={group_id}"
                ],
            )

    return ConflictDecision()
