from __future__ import annotations

from collections import Counter
from functools import lru_cache
from math import sqrt
from pathlib import Path

from app.core.enums import RetrievalSource
from app.eval.dataset import terms
from app.index.build_index import INDEX_METADATA_PATH, read_index_metadata
from app.index.embedding_service import get_embedding_service
from app.index.keyword_store import KeywordStore
from app.index.vector_store import VectorStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.keyword_retriever import KeywordRetriever
from app.retrieval.vector_retriever import VectorRetriever
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk


class BaselineUnavailable(RuntimeError):
    def __init__(self, message: str, *, fatal: bool = True) -> None:
        super().__init__(message)
        self.fatal = fatal


def retrieve_baseline(
    system_name: str,
    query: str,
    chunks: list[Chunk],
    *,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    if system_name == "vector_only":
        return evaluate_vector_only_with_real_stack(query, chunks, top_k=top_k)
    if system_name == "bm25_only":
        return evaluate_bm25_only_with_real_stack(query, chunks, top_k=top_k)
    if system_name == "hybrid_rrf":
        return evaluate_hybrid_rrf_with_real_stack(query, chunks, top_k=top_k)
    if system_name == "hybrid_rrf_rerank":
        return evaluate_hybrid_rrf_rerank_with_real_stack(query, chunks, top_k=top_k)
    raise ValueError(f"Unsupported formal retrieval system: {system_name}")


def retrieve_toy_baseline(
    system_name: str,
    query: str,
    chunks: list[Chunk],
    *,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    if system_name == "toy_vectorish":
        ranked = _rank_vectorish(query, chunks)
        return _to_retrieved(ranked, RetrievalSource.vector, top_k, "vector_score")
    if system_name == "toy_bm25ish":
        ranked = _rank_bm25ish(query, chunks)
        return _to_retrieved(ranked, RetrievalSource.keyword, top_k, "keyword_score")
    if system_name in {
        "toy_hybrid",
        "final_gated",
        "final_gated_calibrated",
        "final_agentic",
        "final_agentic_v2",
        "final_agentic_v2_llm",
    }:
        ranked = _rank_hybrid(
            query,
            chunks,
            rerank=False,
        )
        return _to_retrieved(ranked, RetrievalSource.hybrid, top_k, "rrf_score")
    raise ValueError(f"Unsupported toy retrieval system: {system_name}")


def evaluate_vector_only_with_real_stack(
    query: str,
    chunks: list[Chunk],
    *,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    _require_index_metadata(chunks)
    return _get_vector_retriever().retrieve(query, _retrieval_options(top_k))


def evaluate_bm25_only_with_real_stack(
    query: str,
    chunks: list[Chunk],
    *,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    _require_index_metadata(chunks)
    return _get_keyword_retriever().retrieve(query, _retrieval_options(top_k))


def evaluate_hybrid_rrf_with_real_stack(
    query: str,
    chunks: list[Chunk],
    *,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    _require_index_metadata(chunks)
    return _get_hybrid_retriever().retrieve(query, _retrieval_options(top_k))


def evaluate_hybrid_rrf_rerank_with_real_stack(
    query: str,
    chunks: list[Chunk],
    *,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    hybrid_results = evaluate_hybrid_rrf_with_real_stack(query, chunks, top_k=top_k)
    try:
        reranker = _build_bge_reranker()
    except Exception as exc:
        raise BaselineUnavailable(
            "hybrid_rrf_rerank unavailable because BGE reranker could not be loaded; "
            f"no mock fallback was used. original_error={exc}",
            fatal=False,
        ) from exc
    return reranker.rerank(query, hybrid_results, top_n=top_k)


def _retrieval_options(top_k: int) -> RetrievalOptions:
    return RetrievalOptions(
        top_k_dense=top_k,
        top_k_sparse=top_k,
        top_n_rerank=top_k,
        return_trace=True,
    )


def _require_index_metadata(chunks: list[Chunk]) -> None:
    metadata = read_index_metadata(INDEX_METADATA_PATH)
    if metadata is None:
        raise BaselineUnavailable(
            f"Index metadata not found at {INDEX_METADATA_PATH}. "
            "Run scripts/rebuild_indexes.py before formal retrieval eval."
        )
    expected_count = int(metadata.get("chunk_count") or 0)
    if expected_count != len(chunks):
        raise BaselineUnavailable(
            "Current retrieval index does not match this eval split. "
            f"index_chunk_count={expected_count} split_chunk_count={len(chunks)}. "
            "Rebuild indexes for the target split before running formal baselines."
        )
    if str(metadata.get("embedding_provider")) == "mock":
        raise BaselineUnavailable(
            "Formal retrieval eval requires non-mock embeddings; current index uses mock."
        )
    expected_chunks_path = _expected_chunks_path(chunks)
    indexed_chunks_path = _normalize_path(metadata.get("chunks_path"))
    if expected_chunks_path and indexed_chunks_path != expected_chunks_path:
        raise BaselineUnavailable(
            "Current retrieval index was built from a different chunks file. "
            f"index_chunks_path={indexed_chunks_path or 'missing'} "
            f"expected_chunks_path={expected_chunks_path}. Rebuild indexes for this split."
        )
    whoosh_path = Path(str(metadata.get("whoosh_index_path") or ""))
    if not whoosh_path.exists():
        raise BaselineUnavailable(
            f"Whoosh index path does not exist: {whoosh_path}. Rebuild indexes first."
        )


def _expected_chunks_path(chunks: list[Chunk]) -> str | None:
    if not chunks:
        return None
    doc_ids = {chunk.doc_id for chunk in chunks[:10]}
    corpus_sources = {chunk.corpus_source.value for chunk in chunks[:10]}
    all_corpus_sources = {chunk.corpus_source.value for chunk in chunks}
    if "redteam_injection" in all_corpus_sources:
        return "data/generated/redteam/chunks.jsonl"
    if "hard_negative" in corpus_sources or any(
        doc_id.startswith("hard-negative-") for doc_id in doc_ids
    ):
        return "data/generated/hard_negative/chunks.jsonl"
    if "public_external" in corpus_sources:
        return "data/generated/public/chunks.jsonl"
    if "synthetic_fixture" in corpus_sources:
        return "data/generated/chunks.jsonl"
    return None


def _normalize_path(value: object) -> str:
    return str(value or "").replace("\\", "/")


@lru_cache(maxsize=1)
def _build_bge_reranker():
    from app.rerank.bge_reranker import BGEReranker

    return BGEReranker()


@lru_cache(maxsize=1)
def _get_vector_retriever() -> VectorRetriever:
    return VectorRetriever(get_embedding_service(), VectorStore())


@lru_cache(maxsize=1)
def _get_keyword_retriever() -> KeywordRetriever:
    return KeywordRetriever(KeywordStore())


@lru_cache(maxsize=1)
def _get_hybrid_retriever() -> HybridRetriever:
    return HybridRetriever(
        vector_retriever=_get_vector_retriever(),
        keyword_retriever=_get_keyword_retriever(),
    )


def _rank_vectorish(query: str, chunks: list[Chunk]) -> list[tuple[Chunk, float]]:
    query_terms = Counter(terms(query))
    query_norm = sqrt(sum(weight * weight for weight in query_terms.values())) or 1.0
    ranked: list[tuple[Chunk, float]] = []
    for chunk in chunks:
        chunk_terms = Counter(terms(" ".join([*chunk.section_path, chunk.text])))
        dot = sum(query_terms[term] * chunk_terms.get(term, 0) for term in query_terms)
        chunk_norm = sqrt(sum(weight * weight for weight in chunk_terms.values())) or 1.0
        ranked.append((chunk, dot / (query_norm * chunk_norm)))
    return _stable_sort(ranked)


def _rank_bm25ish(query: str, chunks: list[Chunk]) -> list[tuple[Chunk, float]]:
    query_terms = set(terms(query))
    ranked: list[tuple[Chunk, float]] = []
    for chunk in chunks:
        title = " ".join(chunk.section_path)
        text_terms = terms(chunk.text)
        title_terms = terms(title)
        text_counts = Counter(text_terms)
        score = sum(text_counts.get(term, 0) for term in query_terms)
        score += sum(2 for term in query_terms if term in title_terms)
        score += sum(0.3 for term in query_terms if term in chunk.doc_id.lower())
        ranked.append((chunk, float(score)))
    return _stable_sort(ranked)


def _rank_hybrid(
    query: str,
    chunks: list[Chunk],
    *,
    rerank: bool,
) -> list[tuple[Chunk, float]]:
    vector_rank = {
        chunk.chunk_id: rank
        for rank, (chunk, _) in enumerate(_rank_vectorish(query, chunks), 1)
    }
    keyword_rank = {
        chunk.chunk_id: rank
        for rank, (chunk, _) in enumerate(_rank_bm25ish(query, chunks), 1)
    }
    query_terms = set(terms(query))
    ranked: list[tuple[Chunk, float]] = []
    for chunk in chunks:
        score = 1 / (60 + vector_rank[chunk.chunk_id])
        score += 1 / (60 + keyword_rank[chunk.chunk_id])
        if rerank:
            title_terms = set(terms(" ".join(chunk.section_path)))
            score += 0.02 * len(query_terms & title_terms)
            score += 0.01 * len(query_terms & set(terms(chunk.text[:500])))
        ranked.append((chunk, score))
    return _stable_sort(ranked)


def _stable_sort(ranked: list[tuple[Chunk, float]]) -> list[tuple[Chunk, float]]:
    return sorted(
        ranked,
        key=lambda item: (-item[1], item[0].doc_id, item[0].chunk_index),
    )


def _to_retrieved(
    ranked: list[tuple[Chunk, float]],
    source: RetrievalSource,
    top_k: int,
    score_field: str,
) -> list[RetrievedChunk]:
    retrieved: list[RetrievedChunk] = []
    for rank, (chunk, score) in enumerate(ranked[:top_k], 1):
        retrieved.append(
            RetrievedChunk(
                chunk=chunk,
                source=source,
                rank=rank,
                **{score_field: score},
            )
        )
    return retrieved
