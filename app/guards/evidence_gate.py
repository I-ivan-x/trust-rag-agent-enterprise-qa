from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievedChunk

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}
_STRICT_ENTITY_TERMS = {"ttl", "expiry", "expires", "expiration", "rlimit", "v1", "v2"}


class EvidenceGateConfig(BaseModel):
    min_support_count: int = Field(default=1, ge=0)
    min_score: float | None = None


class EvidenceGateDecision(BaseModel):
    evidence_sufficient: bool
    reason: str
    top_score: float | None = None
    support_count: int = Field(ge=0)
    entity_miss: bool = False
    warnings: list[str] = Field(default_factory=list)


def apply_evidence_gate(
    query: str,
    chunks: list[RetrievedChunk],
    min_support_count: int | None = None,
    min_score: float | None = None,
    config: EvidenceGateConfig | None = None,
) -> EvidenceGateDecision:
    config = config or EvidenceGateConfig()
    min_support_count = (
        config.min_support_count if min_support_count is None else min_support_count
    )
    min_score = config.min_score if min_score is None else min_score

    if min_support_count < 0:
        raise ValueError("min_support_count must be non-negative")
    support_count = len(chunks)
    top_score = _top_score(chunks)
    entity_miss = _has_entity_miss(query, chunks)

    if not chunks:
        return EvidenceGateDecision(
            evidence_sufficient=False,
            reason="no_surviving_chunks",
            top_score=None,
            support_count=0,
            entity_miss=True,
            warnings=["No surviving chunks are available as evidence."],
        )
    if support_count < min_support_count:
        return EvidenceGateDecision(
            evidence_sufficient=False,
            reason="support_count_below_minimum",
            top_score=top_score,
            support_count=support_count,
            entity_miss=entity_miss,
            warnings=[
                f"support_count={support_count} below min_support_count={min_support_count}"
            ],
        )
    if min_score is not None and (top_score is None or top_score < min_score):
        return EvidenceGateDecision(
            evidence_sufficient=False,
            reason="top_score_below_minimum",
            top_score=top_score,
            support_count=support_count,
            entity_miss=entity_miss,
            warnings=[f"top_score={top_score} below min_score={min_score}"],
        )
    if entity_miss:
        return EvidenceGateDecision(
            evidence_sufficient=False,
            reason="entity_miss",
            top_score=top_score,
            support_count=support_count,
            entity_miss=True,
            warnings=["Query key entities do not match surviving evidence."],
        )
    return EvidenceGateDecision(
        evidence_sufficient=True,
        reason="sufficient",
        top_score=top_score,
        support_count=support_count,
        entity_miss=False,
        warnings=[],
    )


def _top_score(chunks: list[RetrievedChunk]) -> float | None:
    scores = [_score(result) for result in chunks]
    scores = [score for score in scores if score is not None]
    return max(scores) if scores else None


def _score(result: RetrievedChunk) -> float | None:
    for score in (
        result.rerank_score,
        result.rrf_score,
        result.vector_score,
        result.keyword_score,
    ):
        if score is not None:
            return float(score)
    return None


def _has_entity_miss(query: str, chunks: list[RetrievedChunk]) -> bool:
    query_terms = _query_terms(query)
    if not query_terms:
        return False
    evidence_terms: set[str] = set()
    for result in chunks:
        evidence_terms.update(_TOKEN_PATTERN.findall(result.chunk.text.lower()))
        for section in result.chunk.section_path:
            evidence_terms.update(_TOKEN_PATTERN.findall(section.lower()))

    overlap = query_terms & evidence_terms
    if not overlap:
        return True
    strict_terms = query_terms & _STRICT_ENTITY_TERMS
    return bool(strict_terms - evidence_terms)


def _query_terms(query: str) -> set[str]:
    terms = set()
    for token in _TOKEN_PATTERN.findall(query.lower()):
        if token in _STOPWORDS:
            continue
        if len(token) >= 3 or token in {"v1", "v2"}:
            terms.add(token)
    return terms


def evidence_gate_config_from_settings(settings) -> EvidenceGateConfig:
    return EvidenceGateConfig(
        min_support_count=getattr(settings, "evidence_min_support_count", 1),
        min_score=getattr(settings, "evidence_min_score", None),
    )
