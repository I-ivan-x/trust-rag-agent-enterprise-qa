from __future__ import annotations

from app.answer.answer_generator import generate_answer
from app.context.context_assembler import ContextChunk, ContextPack
from app.core.enums import (
    AccessLevel,
    CorpusSource,
    DocumentStatus,
    ExpectedBehavior,
    MetadataOrigin,
)
from app.llm.mock_llm import MockLLMClient


def test_mock_llm_generates_structured_answer() -> None:
    context = _context_pack()
    llm = MockLLMClient()

    answer = generate_answer("What is the refresh token rate limit?", context, llm)

    assert answer.answer_text
    assert answer.response_mode == ExpectedBehavior.answer
    assert answer.claims
    assert answer.claims[0].supporting_chunk_ids == ["doc-api-auth-service-v2::chunk-0002"]
    assert answer.raw_model_output is not None


def test_answer_generator_filters_out_of_context_supporting_ids() -> None:
    class BadIdLLM:
        def generate(self, prompt: str) -> str:
            return (
                '{"answer_text":"The limit is 30 requests per minute.",'
                '"claims":[{"claim_id":"claim-0001","text":"The limit is 30 requests '
                'per minute.","supporting_chunk_ids":["missing-chunk"]}]}'
            )

    answer = generate_answer("query", _context_pack(), BadIdLLM())

    assert answer.claims[0].supporting_chunk_ids == []
    assert any("ignored_out_of_context_chunk_ids" in warning for warning in answer.warnings)


def test_empty_context_returns_no_evidence_answer() -> None:
    context = ContextPack(query="query", chunks=[], token_budget=10, estimated_tokens=0)
    answer = generate_answer("query", context, MockLLMClient())

    assert answer.response_mode == ExpectedBehavior.refuse_no_evidence
    assert answer.claims == []
    assert "no_context" in answer.warnings


def test_json_parse_failure_has_deterministic_fallback() -> None:
    class BrokenJsonLLM:
        def generate(self, prompt: str) -> str:
            return "not json"

    first = generate_answer("query", _context_pack(), BrokenJsonLLM())
    second = generate_answer("query", _context_pack(), BrokenJsonLLM())

    assert first == second
    assert first.claims[0].supporting_chunk_ids == ["doc-api-auth-service-v2::chunk-0002"]
    assert "model_output_json_parse_failed" in first.warnings


def _context_pack() -> ContextPack:
    return ContextPack(
        query="What is the refresh token rate limit?",
        chunks=[
            ContextChunk(
                chunk_id="doc-api-auth-service-v2::chunk-0002",
                doc_id="doc-api-auth-service-v2",
                section_path=["Auth Service API v2", "Refresh Token Rate Limit"],
                text=(
                    "The refresh token endpoint is limited to 30 requests per minute per "
                    "client. Requests above this limit receive an HTTP 429 response."
                ),
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
        estimated_tokens=24,
    )
