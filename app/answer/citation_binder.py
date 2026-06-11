from __future__ import annotations

from pydantic import BaseModel, Field

from app.answer.answer_generator import GeneratedAnswer, GeneratedClaim
from app.context.context_assembler import ContextChunk, ContextPack
from app.core.ids import make_citation_id
from app.schemas.citation import Citation, CitationLocator


class BoundClaim(BaseModel):
    claim_id: str
    text: str
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)


class BoundAnswer(BaseModel):
    answer_text: str
    claims: list[BoundClaim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_model_output: str | None = None


def bind_citations(
    generated_answer: GeneratedAnswer,
    context_pack: ContextPack,
) -> BoundAnswer:
    chunk_by_id = {chunk.chunk_id: chunk for chunk in context_pack.chunks}
    citation_by_chunk_id: dict[str, Citation] = {}
    bound_claims: list[BoundClaim] = []
    warnings = list(generated_answer.warnings)

    for claim in generated_answer.claims:
        valid_chunk_ids = [
            chunk_id
            for chunk_id in claim.supporting_chunk_ids
            if chunk_id in chunk_by_id
        ]
        invalid_chunk_ids = [
            chunk_id
            for chunk_id in claim.supporting_chunk_ids
            if chunk_id not in chunk_by_id
        ]
        if invalid_chunk_ids:
            warnings.append(
                f"claim {claim.claim_id} references chunks outside context: "
                f"{', '.join(invalid_chunk_ids)}"
            )
        if not valid_chunk_ids:
            warnings.append(f"claim {claim.claim_id} has no valid supporting chunks")

        citation_ids = []
        for chunk_id in valid_chunk_ids:
            citation = citation_by_chunk_id.get(chunk_id)
            if citation is None:
                citation = _make_citation(
                    chunk_by_id[chunk_id],
                    citation_index=len(citation_by_chunk_id) + 1,
                )
                citation_by_chunk_id[chunk_id] = citation
            citation_ids.append(citation.citation_id)

        bound_claims.append(_bind_claim(claim, valid_chunk_ids, citation_ids))

    return BoundAnswer(
        answer_text=generated_answer.answer_text,
        claims=bound_claims,
        citations=list(citation_by_chunk_id.values()),
        warnings=warnings,
        raw_model_output=generated_answer.raw_model_output,
    )


def _bind_claim(
    claim: GeneratedClaim,
    valid_chunk_ids: list[str],
    citation_ids: list[str],
) -> BoundClaim:
    return BoundClaim(
        claim_id=claim.claim_id,
        text=claim.text,
        supporting_chunk_ids=valid_chunk_ids,
        citation_ids=citation_ids,
    )


def _make_citation(chunk: ContextChunk, citation_index: int) -> Citation:
    return Citation(
        citation_id=make_citation_id(citation_index),
        doc_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        title=chunk.section_path[0] if chunk.section_path else chunk.doc_id,
        section_path=chunk.section_path,
        locator=CitationLocator(
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            source_path=_source_path_hint(chunk),
        ),
    )


def _source_path_hint(chunk: ContextChunk) -> str:
    if chunk.line_start and chunk.line_end:
        return f"{chunk.doc_id}#L{chunk.line_start}-L{chunk.line_end}"
    if chunk.line_start:
        return f"{chunk.doc_id}#L{chunk.line_start}"
    return chunk.doc_id
