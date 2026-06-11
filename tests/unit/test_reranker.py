from __future__ import annotations

import sys
import types

import pytest

from app.core.enums import AccessLevel, DocumentStatus, RetrievalSource
from app.rerank.bge_reranker import BGEReranker
from app.rerank.reranker import MOCK_RERANKER_WARNING, MockReranker, get_reranker
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


def test_mock_reranker_is_deterministic() -> None:
    chunks = [_retrieved("chunk-b", "beta only", 1), _retrieved("chunk-a", "alpha beta", 2)]
    with pytest.warns(RuntimeWarning, match="MockReranker"):
        reranker = MockReranker()

    first = reranker.rerank("alpha", chunks)
    second = reranker.rerank("alpha", chunks)

    assert [item.chunk.chunk_id for item in first] == [item.chunk.chunk_id for item in second]
    assert first[0].chunk.chunk_id == "chunk-a"


def test_rerank_preserves_chunk_metadata_and_scores() -> None:
    chunk = _retrieved("chunk-a", "alpha beta", 1)
    chunk.chunk.allowed_roles.append("engineer")
    with pytest.warns(RuntimeWarning, match="MockReranker"):
        reranker = MockReranker()

    result = reranker.rerank("alpha", [chunk])[0]

    assert result.source == RetrievalSource.rerank
    assert result.rerank_score is not None
    assert result.vector_score == 0.7
    assert result.keyword_score == 3.0
    assert result.rrf_score == 0.5
    assert result.chunk.allowed_roles == ["employee", "engineer"]
    assert result.chunk.status == DocumentStatus.active


def test_reranker_top_n_and_empty_input() -> None:
    chunks = [
        _retrieved("chunk-a", "alpha", 1),
        _retrieved("chunk-b", "beta", 2),
    ]
    with pytest.warns(RuntimeWarning, match="MockReranker"):
        reranker = MockReranker()

    assert len(reranker.rerank("alpha beta", chunks, top_n=1)) == 1
    assert reranker.rerank("alpha", []) == []
    assert reranker.rerank("alpha", chunks, top_n=0) == []


def test_bge_reranker_can_be_constructed_with_cross_encoder(monkeypatch) -> None:
    fake_module = types.ModuleType("sentence_transformers")

    class FakeCrossEncoder:
        def __init__(self, model_name: str, device: str) -> None:
            self.model_name = model_name
            self.device = device

        def predict(self, pairs, show_progress_bar: bool = False):
            return [0.1, 0.9]

    fake_module.CrossEncoder = FakeCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    reranker = BGEReranker(model_name="BAAI/bge-reranker-base")
    results = reranker.rerank(
        "alpha",
        [_retrieved("chunk-a", "alpha", 1), _retrieved("chunk-b", "alpha beta", 2)],
    )

    assert results[0].chunk.chunk_id == "chunk-b"
    assert results[0].rerank_score == 0.9


def test_bge_reranker_does_not_fallback_to_mock(monkeypatch) -> None:
    fake_module = types.ModuleType("sentence_transformers")

    class BrokenCrossEncoder:
        def __init__(self, model_name: str, device: str) -> None:
            raise OSError("model unavailable")

    fake_module.CrossEncoder = BrokenCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    with pytest.raises(RuntimeError, match="BGE reranker model could not be loaded"):
        BGEReranker(model_name="BAAI/bge-reranker-base")

    with pytest.warns(RuntimeWarning, match="MockReranker"):
        assert get_reranker("mock").__class__.__name__ == "MockReranker"
    assert "formal retrieval" in MOCK_RERANKER_WARNING


def _retrieved(chunk_id: str, text: str, rank: int) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        doc_id="doc-test",
        chunk_index=rank - 1,
        text=text,
        section_path=["Doc", "Section"],
        token_count=len(text.split()),
        char_count=len(text),
        line_start=rank,
        line_end=rank,
        status=DocumentStatus.active,
        version="v1",
        allowed_roles=["employee"],
        access_level=AccessLevel.internal,
    )
    return RetrievedChunk(
        chunk=chunk,
        source=RetrievalSource.hybrid,
        vector_score=0.7,
        keyword_score=3.0,
        rrf_score=0.5,
        rank=rank,
    )
