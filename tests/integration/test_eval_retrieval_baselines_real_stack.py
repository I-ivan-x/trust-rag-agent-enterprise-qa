import pytest

import app.eval.baselines as baselines
from app.eval.baselines import (
    BaselineUnavailable,
    evaluate_bm25_only_with_real_stack,
    evaluate_hybrid_rrf_rerank_with_real_stack,
    evaluate_hybrid_rrf_with_real_stack,
    evaluate_vector_only_with_real_stack,
)
from tests.helpers import make_retrieved_chunk


def test_real_stack_vector_baseline_uses_vector_retriever(monkeypatch) -> None:
    calls: list[str] = []

    class FakeVectorRetriever:
        def __init__(self, embedding_service, vector_store):
            del embedding_service, vector_store
            calls.append("init_vector")

        def retrieve(self, query, options):
            del query, options
            calls.append("retrieve_vector")
            return [make_retrieved_chunk("chunk-vector", "vector result")]

    monkeypatch.setattr(baselines, "_require_index_metadata", lambda chunks: None)
    monkeypatch.setattr(baselines, "get_embedding_service", lambda: object())
    monkeypatch.setattr(baselines, "VectorStore", lambda: object())
    monkeypatch.setattr(baselines, "VectorRetriever", FakeVectorRetriever)

    results = evaluate_vector_only_with_real_stack("query", [], top_k=1)

    assert calls == ["init_vector", "retrieve_vector"]
    assert results[0].chunk.chunk_id == "chunk-vector"


def test_real_stack_bm25_baseline_uses_keyword_retriever(monkeypatch) -> None:
    calls: list[str] = []

    class FakeKeywordRetriever:
        def __init__(self, keyword_store):
            del keyword_store
            calls.append("init_keyword")

        def retrieve(self, query, options):
            del query, options
            calls.append("retrieve_keyword")
            return [make_retrieved_chunk("chunk-keyword", "keyword result")]

    monkeypatch.setattr(baselines, "_require_index_metadata", lambda chunks: None)
    monkeypatch.setattr(baselines, "KeywordStore", lambda: object())
    monkeypatch.setattr(baselines, "KeywordRetriever", FakeKeywordRetriever)

    results = evaluate_bm25_only_with_real_stack("query", [], top_k=1)

    assert calls == ["init_keyword", "retrieve_keyword"]
    assert results[0].chunk.chunk_id == "chunk-keyword"


def test_real_stack_hybrid_baseline_uses_hybrid_retriever(monkeypatch) -> None:
    calls: list[str] = []

    class FakeHybridRetriever:
        def __init__(self, vector_retriever, keyword_retriever):
            del vector_retriever, keyword_retriever
            calls.append("init_hybrid")

        def retrieve(self, query, options):
            del query, options
            calls.append("retrieve_hybrid")
            return [make_retrieved_chunk("chunk-hybrid", "hybrid result")]

    monkeypatch.setattr(baselines, "_require_index_metadata", lambda chunks: None)
    monkeypatch.setattr(baselines, "get_embedding_service", lambda: object())
    monkeypatch.setattr(baselines, "VectorStore", lambda: object())
    monkeypatch.setattr(baselines, "KeywordStore", lambda: object())
    monkeypatch.setattr(baselines, "VectorRetriever", lambda *args: object())
    monkeypatch.setattr(baselines, "KeywordRetriever", lambda *args: object())
    monkeypatch.setattr(baselines, "HybridRetriever", FakeHybridRetriever)

    results = evaluate_hybrid_rrf_with_real_stack("query", [], top_k=1)

    assert calls == ["init_hybrid", "retrieve_hybrid"]
    assert results[0].chunk.chunk_id == "chunk-hybrid"


def test_hybrid_rerank_does_not_silently_fallback_to_mock(monkeypatch) -> None:
    monkeypatch.setattr(
        baselines,
        "evaluate_hybrid_rrf_with_real_stack",
        lambda query, chunks, top_k=10: [make_retrieved_chunk("chunk", "result")],
    )
    monkeypatch.setattr(
        baselines,
        "_build_bge_reranker",
        lambda: (_ for _ in ()).throw(RuntimeError("bge missing")),
    )

    with pytest.raises(BaselineUnavailable) as exc_info:
        evaluate_hybrid_rrf_rerank_with_real_stack("query", [], top_k=1)

    assert exc_info.value.fatal is False
    assert "no mock fallback" in str(exc_info.value)

