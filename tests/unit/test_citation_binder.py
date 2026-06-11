from __future__ import annotations

from app.answer.answer_generator import GeneratedAnswer, GeneratedClaim
from app.answer.citation_binder import bind_citations
from app.context.context_assembler import ContextChunk, ContextPack
from app.core.enums import (
    AccessLevel,
    CitationVerificationStatus,
    CorpusSource,
    DocumentStatus,
    MetadataOrigin,
)


def test_bind_citations_maps_claims_to_context_chunks() -> None:
    answer = GeneratedAnswer(
        answer_text="The refresh token endpoint is limited to 30 requests per minute.",
        claims=[
            GeneratedClaim(
                claim_id="claim-0001",
                text="The refresh token endpoint is limited to 30 requests per minute.",
                supporting_chunk_ids=["doc-api-auth-service-v2::chunk-0002"],
            )
        ],
    )

    bound = bind_citations(answer, _context_pack())

    assert bound.claims[0].citation_ids == ["CIT-0001"]
    assert bound.citations[0].chunk_id == "doc-api-auth-service-v2::chunk-0002"
    assert bound.citations[0].doc_id == "doc-api-auth-service-v2"
    assert bound.citations[0].section_path == [
        "Auth Service API v2",
        "Refresh Token Rate Limit",
    ]
    assert bound.citations[0].locator.line_start == 45
    assert bound.citations[0].locator.line_end == 46
    assert bound.citations[0].verification_status == CitationVerificationStatus.unchecked


def test_missing_chunk_id_is_not_bound_and_warns() -> None:
    answer = GeneratedAnswer(
        answer_text="Unsupported claim.",
        claims=[
            GeneratedClaim(
                claim_id="claim-0001",
                text="Unsupported claim.",
                supporting_chunk_ids=["missing-chunk"],
            )
        ],
    )

    bound = bind_citations(answer, _context_pack())

    assert bound.citations == []
    assert bound.claims[0].supporting_chunk_ids == []
    assert any("outside context" in warning for warning in bound.warnings)
    assert any("no valid supporting chunks" in warning for warning in bound.warnings)


def _context_pack() -> ContextPack:
    return ContextPack(
        query="What is the refresh token rate limit?",
        chunks=[
            ContextChunk(
                chunk_id="doc-api-auth-service-v2::chunk-0002",
                doc_id="doc-api-auth-service-v2",
                section_path=["Auth Service API v2", "Refresh Token Rate Limit"],
                text="The refresh token endpoint is limited to 30 requests per minute.",
                status=DocumentStatus.active,
                access_level=AccessLevel.internal,
                allowed_roles=["employee", "engineer"],
                corpus_source=CorpusSource.synthetic_fixture,
                metadata_origin=MetadataOrigin.native,
                line_start=45,
                line_end=46,
                rerank_score=0.9,
                rrf_score=0.2,
                rank=1,
            )
        ],
        token_budget=100,
        estimated_tokens=12,
    )
