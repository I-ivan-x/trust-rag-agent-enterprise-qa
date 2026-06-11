from __future__ import annotations

import re
import warnings
from typing import Protocol

from app.core.config import get_settings
from app.core.enums import RetrievalSource
from app.schemas.retrieval import RetrievedChunk

MOCK_RERANKER_WARNING = (
    "MockReranker is deterministic and for tests/local smoke only; "
    "do not use it for formal retrieval or end-to-end metrics."
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class BaseReranker(Protocol):
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        ...


class MockReranker:
    """Deterministic test/smoke reranker; never use for formal retrieval metrics."""

    def __init__(self) -> None:
        warnings.warn(MOCK_RERANKER_WARNING, RuntimeWarning, stacklevel=2)

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks or top_n == 0:
            return []

        query_terms = set(_TOKEN_PATTERN.findall(query.lower()))
        scored = []
        for original_index, result in enumerate(chunks):
            text_terms = set(_TOKEN_PATTERN.findall(result.chunk.text.lower()))
            overlap = len(query_terms & text_terms)
            prior = result.rrf_score or result.vector_score or result.keyword_score or 0.0
            score = float(overlap) + float(prior) * 0.001
            scored.append((score, result.rank, result.chunk.chunk_id, original_index, result))

        ordered = sorted(scored, key=lambda item: (-item[0], item[1], item[2], item[3]))
        if top_n is not None:
            ordered = ordered[:top_n]

        return [
            result.model_copy(
                update={
                    "source": RetrievalSource.rerank,
                    "rerank_score": score,
                    "rank": rank,
                }
            )
            for rank, (score, *_rest, result) in enumerate(ordered, start=1)
        ]


def get_reranker(provider: str | None = None) -> BaseReranker:
    settings = get_settings()
    selected_provider = (provider or settings.reranker_provider).lower().replace("-", "_")
    if selected_provider == "mock":
        return MockReranker()
    if selected_provider == "bge":
        from app.rerank.bge_reranker import BGEReranker

        return BGEReranker()
    raise ValueError(f"Unsupported reranker provider: {selected_provider}")
