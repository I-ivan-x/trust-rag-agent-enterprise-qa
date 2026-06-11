from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.index.keyword_store import KeywordStore
from app.index.vector_store import VectorStore


class IndexStatus(BaseModel):
    chunks_path: str
    chunks_count: int
    vector_count: int | None
    keyword_count: int | None
    vector_ready: bool
    keyword_ready: bool
    embedding_provider: str
    qdrant_collection: str | None
    whoosh_index_path: str | None
    warnings: list[str] = Field(default_factory=list)


def get_index_status(
    chunks_path: Path | None = None,
    vector_store: VectorStore | None = None,
    keyword_store: KeywordStore | None = None,
) -> IndexStatus:
    settings = get_settings()
    resolved_chunks_path = chunks_path or (settings.generated_dir / "chunks.jsonl")
    warnings: list[str] = []
    chunks_count = 0
    if resolved_chunks_path.exists():
        chunk_lines = resolved_chunks_path.read_text(encoding="utf-8").splitlines()
        chunks_count = sum(1 for line in chunk_lines if line.strip())
    else:
        warnings.append(f"Chunks file does not exist: {resolved_chunks_path}")

    keyword_count: int | None = None
    keyword_ready = False
    try:
        resolved_keyword_store = keyword_store or KeywordStore(settings.whoosh_index_dir)
        keyword_count = resolved_keyword_store.count()
        keyword_ready = keyword_count > 0 and (chunks_count == 0 or keyword_count == chunks_count)
    except Exception as exc:
        warnings.append(f"Whoosh status unavailable: {exc}")

    vector_count: int | None = None
    vector_ready = False
    try:
        resolved_vector_store = vector_store or VectorStore(
            settings.qdrant_url,
            settings.qdrant_collection,
        )
        vector_count = resolved_vector_store.count()
        vector_ready = vector_count > 0 and (chunks_count == 0 or vector_count == chunks_count)
    except Exception as exc:
        warnings.append(f"Qdrant status unavailable: {exc}")

    return IndexStatus(
        chunks_path=resolved_chunks_path.as_posix(),
        chunks_count=chunks_count,
        vector_count=vector_count,
        keyword_count=keyword_count,
        vector_ready=vector_ready,
        keyword_ready=keyword_ready,
        embedding_provider=settings.embedding_provider,
        qdrant_collection=settings.qdrant_collection,
        whoosh_index_path=settings.whoosh_index_dir.as_posix(),
        warnings=warnings,
    )
