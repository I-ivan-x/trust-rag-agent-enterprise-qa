from pathlib import Path

from app.core.enums import RetrievalSource
from app.index.build_index import build_keyword_index, load_chunks_from_jsonl
from app.index.keyword_store import KeywordStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.keyword_retriever import KeywordRetriever
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk
from scripts.ingest_corpus import run_ingest
from scripts.search_preview import run_search_preview


def test_week2_keyword_and_hybrid_retrieval_pipeline(tmp_path: Path) -> None:
    input_dir = tmp_path / "corpus"
    output_dir = tmp_path / "generated"
    whoosh_dir = tmp_path / "whoosh"
    input_dir.mkdir()
    (input_dir / "auth.md").write_text(
        """---
doc_id: doc-auth
title: Auth API
doc_type: api_spec
status: active
version: v1
allowed_roles:
  - employee
---

# Auth API

## Refresh Token Rate Limit
The refresh token endpoint is limited to 30 requests per minute per client.
""",
        encoding="utf-8",
    )

    run_ingest(input_dir=input_dir, output_dir=output_dir, eval_path=None, review_path=None)
    chunks = load_chunks_from_jsonl(output_dir / "chunks.jsonl")
    keyword_store = KeywordStore(whoosh_dir)
    build_keyword_index(chunks, keyword_store)

    keyword_retriever = KeywordRetriever(keyword_store)
    keyword_results = keyword_retriever.retrieve(
        "refresh token",
        RetrievalOptions(top_k_sparse=5),
    )
    assert keyword_results
    assert keyword_results[0].source == RetrievalSource.keyword

    hybrid = HybridRetriever(
        vector_retriever=_FakeVectorRetriever(keyword_results[0]),
        keyword_retriever=keyword_retriever,
    )
    hybrid_results = hybrid.retrieve(
        "refresh token",
        RetrievalOptions(top_k_dense=5, top_k_sparse=5, top_n_rerank=5),
    )
    assert hybrid_results
    assert hybrid_results[0].source == RetrievalSource.hybrid
    assert hybrid_results[0].rrf_score is not None

    preview = run_search_preview(
        "refresh token",
        mode="keyword",
        top_k=3,
        whoosh_index_dir=whoosh_dir,
    )
    assert preview["results"]
    assert preview["results"][0]["chunk_id"] == keyword_results[0].chunk.chunk_id


class _FakeVectorRetriever:
    def __init__(self, result: RetrievedChunk) -> None:
        self.result = result

    def retrieve(
        self,
        query: str,
        options: RetrievalOptions | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        return [
            self.result.model_copy(
                update={
                    "source": RetrievalSource.vector,
                    "vector_score": 0.9,
                    "rank": 1,
                }
            )
        ]

