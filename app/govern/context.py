from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.workflow.state import RetrievalPassResult


class GovernanceControllerContext(BaseModel):
    query: str = ""
    neighborhood: list[dict[str, Any]] = Field(default_factory=list)
    evidence_citations: list[str] = Field(default_factory=list)
    doc_ids: list[str] = Field(default_factory=list)
    conflict_doc_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_pass_result(cls, pass_result: RetrievalPassResult) -> GovernanceControllerContext:
        neighborhood: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        for result in [
            *pass_result.acl_decision.surviving_chunks,
            *pass_result.reranked_chunks,
            *pass_result.state_decision.deprecated_chunks,
            *pass_result.conflict_decision.conflicting_chunks,
        ]:
            chunk = result.chunk
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            neighborhood.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "status": chunk.status.value,
                    "section_path": chunk.section_path,
                }
            )
        return cls(
            query=pass_result.query,
            neighborhood=neighborhood,
            evidence_citations=[item["chunk_id"] for item in neighborhood[:5]],
            doc_ids=sorted({item["doc_id"] for item in neighborhood}),
            conflict_doc_ids=sorted(
                {result.chunk.doc_id for result in pass_result.conflict_decision.conflicting_chunks}
            ),
        )
