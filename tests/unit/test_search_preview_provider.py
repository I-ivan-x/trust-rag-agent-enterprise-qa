from pathlib import Path

from app.index.build_index import build_index_metadata, write_index_metadata
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk
from scripts import search_preview


def test_search_preview_uses_index_metadata_provider_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    metadata_path = _write_metadata(tmp_path, provider="sentence_transformer", vector_size=384)
    captured: dict[str, str | None] = {}

    def fake_get_embedding_service(provider: str | None = None) -> _FakeEmbeddingService:
        captured["provider"] = provider
        return _FakeEmbeddingService(dimension=384)

    monkeypatch.setattr(search_preview, "get_embedding_service", fake_get_embedding_service)
    monkeypatch.setattr(search_preview, "VectorStore", _FakeVectorStore)

    preview = search_preview.run_search_preview(
        "refresh token rate limit",
        mode="vector",
        index_metadata_path=metadata_path,
    )

    assert captured["provider"] == "sentence_transformer"
    assert preview["query_embedding_provider"] == "sentence_transformer"
    assert preview["index_embedding_provider"] == "sentence_transformer"
    assert preview["index_vector_size"] == 384
    assert preview["results"][0]["chunk_id"] == "doc-api-auth-service-v2::chunk-0002"


def test_search_preview_warns_on_provider_mismatch(tmp_path: Path, monkeypatch) -> None:
    metadata_path = _write_metadata(tmp_path, provider="sentence_transformer", vector_size=384)

    monkeypatch.setattr(
        search_preview,
        "get_embedding_service",
        lambda provider=None: _FakeEmbeddingService(dimension=16),
    )
    monkeypatch.setattr(search_preview, "VectorStore", _FakeVectorStore)

    preview = search_preview.run_search_preview(
        "refresh token rate limit",
        mode="vector",
        embedding_provider="mock",
        index_metadata_path=metadata_path,
    )

    warnings = "\n".join(preview["warnings"])
    assert "Query embedding provider differs from index metadata" in warnings
    assert "mock / 16d" in warnings
    assert "Mock embedding is for tests/smoke only" in warnings


def test_search_preview_warns_when_mock_provider_is_used(tmp_path: Path, monkeypatch) -> None:
    metadata_path = _write_metadata(tmp_path, provider="mock", vector_size=16)

    monkeypatch.setattr(
        search_preview,
        "get_embedding_service",
        lambda provider=None: _FakeEmbeddingService(dimension=16),
    )
    monkeypatch.setattr(search_preview, "VectorStore", _FakeVectorStore)

    preview = search_preview.run_search_preview(
        "refresh token rate limit",
        mode="vector",
        index_metadata_path=metadata_path,
    )

    assert any(
        "Mock embedding is for tests/smoke only" in warning
        for warning in preview["warnings"]
    )


def _write_metadata(tmp_path: Path, provider: str, vector_size: int) -> Path:
    path = tmp_path / "index_metadata.json"
    metadata = build_index_metadata(
        embedding_provider=provider,
        embedding_model_name=(
            "mock-embedding-v0" if provider == "mock" else "BAAI/bge-small-en-v1.5"
        ),
        vector_size=vector_size,
        qdrant_collection="trust_rag_enterprise_qa",
        chunk_count=11,
        keyword_count=11,
        vector_count=11,
        whoosh_index_path="data/indexes/whoosh",
    )
    write_index_metadata(path, metadata)
    return path


class _FakeEmbeddingService:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dimension for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]


class _FakeVectorStore:
    def __init__(self, qdrant_url: str | None = None, collection_name: str | None = None) -> None:
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        chunk = Chunk(
            chunk_id="doc-api-auth-service-v2::chunk-0002",
            doc_id="doc-api-auth-service-v2",
            chunk_index=2,
            text="The refresh token endpoint is limited to 30 requests per minute per client.",
            section_path=["Auth Service API v2", "Refresh Token Rate Limit"],
            status="active",
            version="v2",
            allowed_roles=["employee"],
            access_level="internal",
        )
        return [
            RetrievedChunk(
                chunk=chunk,
                source="vector",
                vector_score=0.99,
                rank=1,
            )
        ]
