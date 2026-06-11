from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.eval.dataset import terms
from app.schemas.citation import Citation
from app.schemas.retrieval import RetrievedChunk


class CitationAuditResult(BaseModel):
    citation_valid: bool
    supports_core_claim: bool
    invalid_citations: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    checked_citation_count: int = 0
    note: str = "Rule-based v1 citation audit; not a substitute for human review."


def verify_citations(
    *,
    claims: list[str],
    citations: list[Citation | dict[str, Any]],
    retrieved_chunks: list[RetrievedChunk],
) -> CitationAuditResult:
    chunk_by_id = {item.chunk.chunk_id: item.chunk for item in retrieved_chunks}
    normalized_citations = [
        citation if isinstance(citation, Citation) else Citation.model_validate(citation)
        for citation in citations
    ]
    invalid: list[str] = []
    reasons: list[str] = []

    for citation in normalized_citations:
        chunk = chunk_by_id.get(citation.chunk_id)
        if chunk is None:
            invalid.append(citation.citation_id)
            reasons.append(f"{citation.citation_id}: chunk_id not present in retrieved context")
            continue
        if chunk.doc_id != citation.doc_id:
            invalid.append(citation.citation_id)
            reasons.append(f"{citation.citation_id}: doc_id does not match cited chunk")

    unsupported = [
        claim
        for claim in claims
        if not _claim_supported_by_any_chunk(claim, list(chunk_by_id.values()))
    ]
    if unsupported:
        reasons.append("one or more reference claims have weak keyword overlap")

    has_required_citation = bool(normalized_citations) if claims else True
    citation_valid = has_required_citation and not invalid
    supports_core_claim = bool(claims) and len(unsupported) < len(claims)
    if claims and not normalized_citations:
        reasons.append("answer has claims but no citations")

    return CitationAuditResult(
        citation_valid=citation_valid,
        supports_core_claim=supports_core_claim,
        invalid_citations=invalid,
        unsupported_claims=unsupported,
        failure_reasons=reasons,
        checked_citation_count=len(normalized_citations),
    )


def _claim_supported_by_any_chunk(claim: str, chunks: list[Any]) -> bool:
    claim_terms = set(terms(claim))
    if not claim_terms:
        return True
    for chunk in chunks:
        chunk_terms = set(terms(chunk.text))
        overlap = len(claim_terms & chunk_terms) / len(claim_terms)
        if overlap >= 0.25:
            return True
    return False

