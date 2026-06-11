from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import RetrievalSource
from app.retrieval.keyword_retriever import KeywordRetriever
from app.retrieval.vector_retriever import VectorRetriever
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk


def rrf_fuse(
    result_lists: list[list[RetrievedChunk]],
    k: int = 60,
    top_n: int | None = None,
) -> list[RetrievedChunk]:
    fused: dict[str, _Accumulator] = {}
    for result_list in result_lists:
        for result in result_list:
            chunk_id = result.chunk.chunk_id
            accumulator = fused.setdefault(chunk_id, _Accumulator(result=result))
            accumulator.rrf_score += 1 / (k + result.rank)
            accumulator.best_rank = min(accumulator.best_rank, result.rank)
            if result.vector_score is not None:
                accumulator.vector_score = result.vector_score
            if result.keyword_score is not None:
                accumulator.keyword_score = result.keyword_score

    ordered = sorted(
        fused.values(),
        key=lambda item: (-item.rrf_score, item.best_rank, item.result.chunk.chunk_id),
    )
    if top_n is not None:
        ordered = ordered[:top_n]

    return [
        RetrievedChunk(
            chunk=item.result.chunk,
            source=RetrievalSource.hybrid,
            vector_score=item.vector_score,
            keyword_score=item.keyword_score,
            rrf_score=item.rrf_score,
            rank=rank,
        )
        for rank, item in enumerate(ordered, start=1)
    ]


class HybridRetriever:
    def __init__(
        self,
        vector_retriever: VectorRetriever | None = None,
        keyword_retriever: KeywordRetriever | None = None,
    ) -> None:
        self.vector_retriever = vector_retriever
        self.keyword_retriever = keyword_retriever
        self.last_warnings: list[str] = []

    def retrieve(
        self,
        query: str,
        options: RetrievalOptions | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        retrieval_options = options or RetrievalOptions()
        self.last_warnings = []
        result_lists: list[list[RetrievedChunk]] = []

        if self.vector_retriever is not None and retrieval_options.top_k_dense > 0:
            try:
                result_lists.append(
                    self.vector_retriever.retrieve(query, retrieval_options, filters=filters)
                )
            except Exception as exc:
                self.last_warnings.append(f"Vector retrieval unavailable: {exc}")

        if self.keyword_retriever is not None and retrieval_options.top_k_sparse > 0:
            result_lists.append(
                self.keyword_retriever.retrieve(query, retrieval_options, filters=filters)
            )

        return rrf_fuse(
            result_lists,
            top_n=retrieval_options.top_n_rerank,
        )


@dataclass
class _Accumulator:
    result: RetrievedChunk
    rrf_score: float = 0.0
    best_rank: int = 1_000_000
    vector_score: float | None = None
    keyword_score: float | None = None

