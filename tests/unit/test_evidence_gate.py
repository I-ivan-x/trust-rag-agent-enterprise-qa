from __future__ import annotations

from app.guards.evidence_gate import apply_evidence_gate
from app.retrieval.query_rewriter import rewrite_query_for_evidence
from tests.helpers import make_retrieved_chunk


def test_no_chunks_are_insufficient() -> None:
    decision = apply_evidence_gate("unknown query", [])

    assert decision.evidence_sufficient is False
    assert decision.reason == "no_surviving_chunks"


def test_enough_matching_chunks_are_sufficient() -> None:
    chunk = make_retrieved_chunk(
        "chunk-rate-limit",
        "The refresh token endpoint is limited to 30 requests per minute.",
        section_path=["Auth Service API v2", "Refresh Token Rate Limit"],
        rerank_score=0.8,
    )

    decision = apply_evidence_gate("What is the refresh token rate limit?", [chunk])

    assert decision.evidence_sufficient is True
    assert decision.reason == "sufficient"


def test_low_score_is_insufficient() -> None:
    chunk = make_retrieved_chunk("chunk-low", "Refresh token rate limit.", rerank_score=0.1)

    decision = apply_evidence_gate("refresh token rate limit", [chunk], min_score=0.5)

    assert decision.evidence_sufficient is False
    assert decision.reason == "top_score_below_minimum"


def test_support_count_insufficient() -> None:
    chunk = make_retrieved_chunk("chunk-one", "Refresh token rate limit.", rerank_score=0.9)

    decision = apply_evidence_gate("refresh token rate limit", [chunk], min_support_count=2)

    assert decision.evidence_sufficient is False
    assert decision.reason == "support_count_below_minimum"


def test_entity_miss_is_insufficient() -> None:
    chunk = make_retrieved_chunk("chunk-auth", "The access token lifetime is 30 minutes.")

    decision = apply_evidence_gate("kubernetes autoscaling policy", [chunk])

    assert decision.evidence_sufficient is False
    assert decision.reason == "entity_miss"


def test_rewrite_trigger_condition_for_ttl() -> None:
    chunk = make_retrieved_chunk("chunk-auth", "The access token lifetime is 30 minutes.")

    evidence = apply_evidence_gate("token ttl", [chunk])
    rewrite = rewrite_query_for_evidence("token ttl")

    assert evidence.evidence_sufficient is False
    assert evidence.entity_miss is True
    assert rewrite.should_rewrite is True
    assert rewrite.rewritten_query == "access token lifetime"


def test_version_miss_is_insufficient() -> None:
    chunk = make_retrieved_chunk(
        "chunk-v2",
        "In v2 the access token lifetime is 30 minutes.",
    )

    decision = apply_evidence_gate("What was the v1 access token lifetime?", [chunk])

    assert decision.evidence_sufficient is False
    assert decision.reason == "entity_miss"
