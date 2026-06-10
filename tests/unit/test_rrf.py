from app.core.enums import RetrievalSource
from app.retrieval.hybrid_retriever import HybridRetriever, rrf_fuse
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


def test_rrf_fuses_and_deduplicates_chunks() -> None:
    shared_vector = _retrieved("shared", RetrievalSource.vector, rank=1, vector_score=0.9)
    vector_only = _retrieved("vector-only", RetrievalSource.vector, rank=2, vector_score=0.8)
    shared_keyword = _retrieved("shared", RetrievalSource.keyword, rank=2, keyword_score=4.0)
    keyword_only = _retrieved("keyword-only", RetrievalSource.keyword, rank=1, keyword_score=5.0)

    fused = rrf_fuse([[shared_vector, vector_only], [keyword_only, shared_keyword]], top_n=3)

    assert [result.rank for result in fused] == [1, 2, 3]
    assert fused[0].chunk.chunk_id == "shared"
    assert fused[0].source == RetrievalSource.hybrid
    assert fused[0].vector_score == 0.9
    assert fused[0].keyword_score == 4.0
    assert fused[0].rrf_score is not None
    assert len({result.chunk.chunk_id for result in fused}) == len(fused)


def test_rrf_supports_single_side_and_empty_lists() -> None:
    single_side = rrf_fuse([[_retrieved("a", RetrievalSource.keyword, rank=1)]])
    empty = rrf_fuse([[]])

    assert len(single_side) == 1
    assert single_side[0].rank == 1
    assert empty == []


def test_rrf_top_n_truncates_deterministically() -> None:
    results = rrf_fuse(
        [
            [
                _retrieved("b", RetrievalSource.vector, rank=1),
                _retrieved("a", RetrievalSource.vector, rank=2),
            ]
        ],
        top_n=1,
    )

    assert len(results) == 1
    assert results[0].chunk.chunk_id == "b"


def test_hybrid_warning_includes_vector_branch_root_cause() -> None:
    hybrid = HybridRetriever(vector_retriever=_FailingVectorRetriever(), keyword_retriever=None)

    results = hybrid.retrieve("refresh token")

    assert results == []
    assert hybrid.last_warnings
    assert "vector dimension mismatch" in hybrid.last_warnings[0]
    assert "original_error=expected dim 384 got 16" in hybrid.last_warnings[0]


def _retrieved(
    chunk_id: str,
    source: RetrievalSource,
    rank: int,
    vector_score: float | None = None,
    keyword_score: float | None = None,
) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        doc_id=f"doc-{chunk_id}",
        chunk_index=0,
        text=f"text for {chunk_id}",
        section_path=["Doc"],
        status="active",
        version="v1",
        allowed_roles=["employee"],
        access_level="internal",
    )
    return RetrievedChunk(
        chunk=chunk,
        source=source,
        vector_score=vector_score,
        keyword_score=keyword_score,
        rank=rank,
    )


class _FailingVectorRetriever:
    def retrieve(self, query, options=None, filters=None):
        raise RuntimeError(
            "Qdrant search failed: vector dimension mismatch. "
            "original_error=expected dim 384 got 16"
        )

