from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.index.embedding_service import BaseEmbeddingService
from app.index.keyword_store import KeywordStore
from app.index.vector_store import VectorStore
from app.schemas.chunk import Chunk

INDEX_METADATA_PATH = Path("data/indexes/index_metadata.json")
MOCK_EMBEDDING_MODEL_NAME = "mock-embedding-v0"
MOCK_EMBEDDING_WARNING = (
    "Mock embedding is for tests/smoke only and must not be used for formal retrieval metrics."
)


def load_chunks_from_jsonl(path: Path) -> list[Chunk]:
    if not path.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {path}. Run scripts/ingest_corpus.py first."
        )
    chunks: list[Chunk] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            chunks.append(Chunk.model_validate_json(line))
    return chunks


def build_vector_index(
    chunks: list[Chunk],
    embedding_service: BaseEmbeddingService,
    vector_store: VectorStore,
) -> dict[str, Any]:
    vectors = embedding_service.embed_texts([chunk.text for chunk in chunks])
    vector_size = len(vectors[0]) if vectors else 0
    if vector_size <= 0 and chunks:
        raise ValueError("Embedding service returned empty vectors")
    if vector_size > 0:
        vector_store.recreate_collection(vector_size=vector_size)
        vector_store.upsert_chunks(chunks, vectors)
    return {
        "vector_index_built": True,
        "vector_count": vector_store.count() if vector_size > 0 else 0,
        "vector_size": vector_size,
    }


def build_keyword_index(
    chunks: list[Chunk],
    keyword_store: KeywordStore,
) -> dict[str, Any]:
    keyword_store.recreate_index()
    keyword_store.index_chunks(chunks)
    return {
        "keyword_index_built": True,
        "keyword_count": keyword_store.count(),
    }


def build_all_indexes(
    chunks_path: Path,
    embedding_service: BaseEmbeddingService,
    vector_store: VectorStore,
    keyword_store: KeywordStore,
) -> dict[str, Any]:
    settings = get_settings()
    chunks = load_chunks_from_jsonl(chunks_path)
    keyword_summary = build_keyword_index(chunks, keyword_store)
    vector_summary: dict[str, Any]
    try:
        vector_summary = build_vector_index(chunks, embedding_service, vector_store)
        vector_warning = None
    except Exception as exc:
        vector_summary = {
            "vector_index_built": False,
            "vector_count": None,
            "vector_size": None,
        }
        vector_warning = str(exc)

    summary = {
        "chunks_loaded": len(chunks),
        **vector_summary,
        **keyword_summary,
        "embedding_provider": settings.embedding_provider,
        "embedding_model_name": get_embedding_model_name(settings.embedding_provider),
        "qdrant_collection": settings.qdrant_collection,
        "whoosh_index_path": keyword_store.index_dir.as_posix(),
        "warnings": [vector_warning] if vector_warning else [],
    }
    return json.loads(json.dumps(summary))


def canonical_embedding_provider(provider: str | None) -> str:
    selected = (provider or get_settings().embedding_provider).lower().replace("-", "_")
    if selected == "sentence_transformer":
        return "sentence_transformer"
    if selected == "mock":
        return "mock"
    if selected in {"openai", "openai_compatible"}:
        return "openai_compatible"
    return selected


def get_embedding_model_name(provider: str | None) -> str:
    selected = canonical_embedding_provider(provider)
    if selected == "mock":
        return MOCK_EMBEDDING_MODEL_NAME
    return get_settings().embedding_model_name


def infer_embedding_vector_size(
    embedding_service: BaseEmbeddingService,
    chunks: list[Chunk],
) -> int | None:
    probe_text = chunks[0].text if chunks else "embedding dimension probe"
    try:
        return len(embedding_service.embed_query(probe_text))
    except Exception:
        return None


def build_index_metadata(
    *,
    embedding_provider: str,
    embedding_model_name: str,
    vector_size: int | None,
    qdrant_collection: str,
    chunk_count: int,
    keyword_count: int | None,
    vector_count: int | None,
    whoosh_index_path: str,
    chunks_path: str | None = None,
) -> dict[str, Any]:
    return {
        "embedding_provider": canonical_embedding_provider(embedding_provider),
        "embedding_model_name": embedding_model_name,
        "vector_size": vector_size,
        "qdrant_collection": qdrant_collection,
        "chunk_count": chunk_count,
        "keyword_count": keyword_count,
        "vector_count": vector_count,
        "whoosh_index_path": whoosh_index_path,
        "chunks_path": chunks_path,
        "built_at": datetime.now(UTC).isoformat(),
    }


def write_index_metadata(path: Path, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_index_metadata(path: Path = INDEX_METADATA_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
