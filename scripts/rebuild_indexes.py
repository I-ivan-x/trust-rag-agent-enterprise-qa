# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.index.build_index import (
    INDEX_METADATA_PATH,
    MOCK_EMBEDDING_WARNING,
    build_index_metadata,
    build_keyword_index,
    build_vector_index,
    canonical_embedding_provider,
    get_embedding_model_name,
    infer_embedding_vector_size,
    load_chunks_from_jsonl,
    write_index_metadata,
)
from app.index.embedding_service import get_embedding_service
from app.index.keyword_store import KeywordStore
from app.index.vector_store import VectorStore


def rebuild_indexes(
    chunks_path: Path,
    embedding_provider: str | None = None,
    whoosh_index_dir: Path | None = None,
    include_redteam: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {chunks_path}. Run python -m uv run python "
            "scripts/ingest_corpus.py first."
        )

    chunks = load_chunks_from_jsonl(chunks_path)
    keyword_store = KeywordStore(whoosh_index_dir or settings.whoosh_index_dir)
    keyword_summary = build_keyword_index(chunks, keyword_store)

    provider = canonical_embedding_provider(embedding_provider or settings.embedding_provider)
    embedding_model_name = get_embedding_model_name(provider)
    vector_summary: dict[str, Any]
    warnings: list[str] = []
    if provider == "mock":
        warnings.append(MOCK_EMBEDDING_WARNING)
    embedding_service = None
    try:
        embedding_service = get_embedding_service(provider)
        vector_store = VectorStore(settings.qdrant_url, settings.qdrant_collection)
        vector_summary = build_vector_index(chunks, embedding_service, vector_store)
    except Exception as exc:
        vector_summary = {
            "vector_index_built": False,
            "vector_count": None,
            "vector_size": None,
        }
        warnings.append(
            "Qdrant vector index was not validated because local Qdrant service "
            f"is unavailable or embedding setup failed: {exc}"
        )

    if vector_summary["vector_size"] is None and embedding_service is not None:
        vector_summary["vector_size"] = infer_embedding_vector_size(embedding_service, chunks)

    metadata = build_index_metadata(
        embedding_provider=provider,
        embedding_model_name=embedding_model_name,
        vector_size=vector_summary["vector_size"],
        qdrant_collection=settings.qdrant_collection,
        chunk_count=len(chunks),
        keyword_count=keyword_summary["keyword_count"],
        vector_count=vector_summary["vector_count"],
        whoosh_index_path=keyword_store.index_dir.as_posix(),
        chunks_path=chunks_path.as_posix(),
    )
    write_index_metadata(INDEX_METADATA_PATH, metadata)

    return {
        "chunks_loaded": len(chunks),
        **vector_summary,
        **keyword_summary,
        "embedding_provider": provider,
        "embedding_model_name": embedding_model_name,
        "qdrant_collection": settings.qdrant_collection,
        "whoosh_index_path": keyword_store.index_dir.as_posix(),
        "chunks_path": chunks_path.as_posix(),
        "include_redteam": include_redteam,
        "index_metadata_path": INDEX_METADATA_PATH.as_posix(),
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild Week 2 retrieval indexes.")
    parser.add_argument("--chunks", type=Path, default=Path("data/generated/chunks.jsonl"))
    parser.add_argument(
        "--embedding-provider",
        choices=["mock", "sentence_transformer", "openai_compatible"],
        default=None,
    )
    parser.add_argument("--whoosh-index-dir", type=Path, default=None)
    parser.add_argument(
        "--include-redteam",
        action="store_true",
        help=(
            "Build from data/generated/redteam/chunks.jsonl when --chunks is not "
            "overridden. Default is off so redteam corpus never enters normal indexes."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    chunks_path = (
        Path("data/generated/redteam/chunks.jsonl")
        if args.include_redteam and args.chunks == Path("data/generated/chunks.jsonl")
        else args.chunks
    )
    try:
        summary = rebuild_indexes(
            chunks_path=chunks_path,
            embedding_provider=args.embedding_provider,
            whoosh_index_dir=args.whoosh_index_dir,
            include_redteam=args.include_redteam,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
