from __future__ import annotations

from app.retrieval.query_rewriter import rewrite_query_for_evidence


def test_token_ttl_rewrites_to_access_token_lifetime() -> None:
    decision = rewrite_query_for_evidence("token ttl")

    assert decision.should_rewrite is True
    assert decision.rewritten_query == "access token lifetime"


def test_refresh_limit_rewrites_to_refresh_token_rate_limit() -> None:
    decision = rewrite_query_for_evidence("refresh limit")

    assert decision.should_rewrite is True
    assert decision.rewritten_query == "refresh token rate limit"


def test_refresh_rlimit_rewrites_to_refresh_token_rate_limit() -> None:
    decision = rewrite_query_for_evidence("refresh rlimit")

    assert decision.should_rewrite is True
    assert decision.rewritten_query == "refresh token rate limit"


def test_unchanged_query_does_not_rewrite() -> None:
    decision = rewrite_query_for_evidence("access token lifetime")

    assert decision.should_rewrite is False
    assert decision.rewritten_query is None


def test_rewrite_is_idempotent_for_max_one_round() -> None:
    first = rewrite_query_for_evidence("token expiry")
    second = rewrite_query_for_evidence(first.rewritten_query or "")

    assert first.should_rewrite is True
    assert second.should_rewrite is False
