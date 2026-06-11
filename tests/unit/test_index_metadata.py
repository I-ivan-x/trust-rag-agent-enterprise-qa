from pathlib import Path

from app.index.build_index import (
    build_index_metadata,
    get_embedding_model_name,
    read_index_metadata,
    write_index_metadata,
)


def test_index_metadata_write_and_read(tmp_path: Path) -> None:
    path = tmp_path / "index_metadata.json"
    metadata = build_index_metadata(
        embedding_provider="mock",
        embedding_model_name=get_embedding_model_name("mock"),
        vector_size=16,
        qdrant_collection="trust_rag_enterprise_qa",
        chunk_count=11,
        keyword_count=11,
        vector_count=None,
        whoosh_index_path="data/indexes/whoosh",
    )

    write_index_metadata(path, metadata)
    loaded = read_index_metadata(path)

    assert loaded is not None
    assert loaded["embedding_provider"] == "mock"
    assert loaded["embedding_model_name"] == "mock-embedding-v0"
    assert "BGE" not in loaded["embedding_model_name"]
    assert loaded["vector_size"] == 16
    assert loaded["built_at"]


def test_sentence_transformer_metadata_expresses_model_and_vector_size() -> None:
    metadata = build_index_metadata(
        embedding_provider="sentence_transformer",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        vector_size=384,
        qdrant_collection="trust_rag_enterprise_qa",
        chunk_count=11,
        keyword_count=11,
        vector_count=11,
        whoosh_index_path="data/indexes/whoosh",
    )

    assert metadata["embedding_provider"] == "sentence_transformer"
    assert metadata["embedding_model_name"] == "BAAI/bge-small-en-v1.5"
    assert metadata["vector_size"] == 384

