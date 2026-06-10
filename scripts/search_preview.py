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
    canonical_embedding_provider,
    get_embedding_model_name,
    read_index_metadata,
)
from app.index.embedding_service import get_embedding_service
from app.index.keyword_store import KeywordStore
from app.index.vector_store import VectorStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.keyword_retriever import KeywordRetriever
from app.retrieval.vector_retriever import VectorRetriever
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk

REBUILD_HINT = (
    "Index not ready. Run: python -m uv run python scripts/ingest_corpus.py && "
    "python -m uv run python scripts/rebuild_indexes.py --embedding-provider "
    "sentence_transformer"
)


def run_search_preview(
    query: str,
    mode: str = "hybrid",
    top_k: int = 5,
    embedding_provider: str | None = None,
    whoosh_index_dir: Path | None = None,
    index_metadata_path: Path = INDEX_METADATA_PATH,
) -> dict[str, Any]:
    settings = get_settings()
    options = RetrievalOptions(top_k_dense=top_k, top_k_sparse=top_k, top_n_rerank=top_k)
    keyword_store = KeywordStore(whoosh_index_dir or settings.whoosh_index_dir)
    keyword_retriever = KeywordRetriever(keyword_store)
    index_metadata = read_index_metadata(index_metadata_path)
    query_provider, warnings = _resolve_query_provider(
        explicit_provider=embedding_provider,
        index_metadata=index_metadata,
        mode=mode,
    )

    if mode == "keyword":
        results = keyword_retriever.retrieve(query, options)
    elif mode == "vector":
        vector_retriever = _make_vector_retriever(query_provider)
        try:
            results = vector_retriever.retrieve(query, options)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc}\n{_provider_guidance(index_metadata, query_provider, query, mode)}"
            ) from exc
    elif mode == "hybrid":
        try:
            vector_retriever = _make_vector_retriever(query_provider)
        except Exception as exc:
            vector_retriever = None
            warnings.append(f"Vector retriever unavailable: {exc}")
        hybrid_retriever = HybridRetriever(
            vector_retriever=vector_retriever,
            keyword_retriever=keyword_retriever,
        )
        results = hybrid_retriever.retrieve(query, options)
        warnings.extend(hybrid_retriever.last_warnings)
        if vector_retriever is None or hybrid_retriever.last_warnings:
            warnings.append(_provider_guidance(index_metadata, query_provider, query, mode))
    else:
        raise ValueError(f"Unsupported search mode: {mode}")

    return {
        "query": query,
        "mode": mode,
        "top_k": top_k,
        "index_embedding_provider": _metadata_value(index_metadata, "embedding_provider"),
        "index_embedding_model_name": _metadata_value(index_metadata, "embedding_model_name"),
        "index_vector_size": _metadata_value(index_metadata, "vector_size"),
        "query_embedding_provider": query_provider,
        "query_embedding_model_name": get_embedding_model_name(query_provider),
        "index_metadata_path": index_metadata_path.as_posix(),
        "warnings": warnings,
        "results": [_result_to_preview(result) for result in results],
    }


def _make_vector_retriever(embedding_provider: str | None = None) -> VectorRetriever:
    settings = get_settings()
    embedding_service = get_embedding_service(embedding_provider)
    vector_store = VectorStore(settings.qdrant_url, settings.qdrant_collection)
    return VectorRetriever(embedding_service, vector_store)


def _resolve_query_provider(
    explicit_provider: str | None,
    index_metadata: dict[str, Any] | None,
    mode: str,
) -> tuple[str, list[str]]:
    settings = get_settings()
    warnings: list[str] = []
    index_provider = _metadata_value(index_metadata, "embedding_provider")

    if explicit_provider is None and index_provider:
        query_provider = canonical_embedding_provider(str(index_provider))
    else:
        query_provider = canonical_embedding_provider(
            explicit_provider or settings.embedding_provider
        )

    if explicit_provider is None and not index_provider and mode in {"vector", "hybrid"}:
        warnings.append(
            "No index metadata found; using configured embedding provider "
            f"{query_provider}. Pass --embedding-provider explicitly if this is not correct."
        )

    if explicit_provider is not None and index_provider:
        index_provider = canonical_embedding_provider(str(index_provider))
        if query_provider != index_provider:
            warnings.append(
                "Query embedding provider differs from index metadata: "
                f"index_provider={index_provider} query_provider={query_provider}. "
                f"{_provider_guidance(index_metadata, query_provider, '<query>', mode)}"
            )

    if query_provider == "mock" and mode in {"vector", "hybrid"}:
        warnings.append(MOCK_EMBEDDING_WARNING)
    return query_provider, warnings


def _provider_guidance(
    index_metadata: dict[str, Any] | None,
    query_provider: str,
    query: str,
    mode: str,
) -> str:
    index_provider = _metadata_value(index_metadata, "embedding_provider")
    index_vector_size = _metadata_value(index_metadata, "vector_size")
    if index_provider:
        command_query = query if query != "<query>" else "..."
        query_vector_size = _provider_vector_size_hint(query_provider, index_metadata)
        return (
            "Embedding provider guidance: "
            f"Current index was built with {index_provider} / {index_vector_size}d. "
            f"Your query provider is {query_provider} / {query_vector_size}. Run: "
            f'python -m uv run python scripts/search_preview.py "{command_query}" '
            f"--mode {mode} --embedding-provider {index_provider}"
        )
    return (
        "Embedding provider guidance: no index metadata found. Rebuild indexes or pass "
        "--embedding-provider explicitly."
    )


def _metadata_value(index_metadata: dict[str, Any] | None, key: str) -> Any:
    return index_metadata.get(key) if index_metadata else None


def _provider_vector_size_hint(
    query_provider: str,
    index_metadata: dict[str, Any] | None,
) -> str:
    index_provider = _metadata_value(index_metadata, "embedding_provider")
    if query_provider == "mock":
        return "16d"
    if query_provider == index_provider and _metadata_value(index_metadata, "vector_size"):
        return f"{_metadata_value(index_metadata, 'vector_size')}d"
    return "unknown dimension"


def _result_to_preview(result: RetrievedChunk) -> dict[str, Any]:
    score = result.rrf_score
    if score is None:
        score = result.vector_score if result.vector_score is not None else result.keyword_score
    return {
        "rank": result.rank,
        "score": score,
        "chunk_id": result.chunk.chunk_id,
        "doc_id": result.chunk.doc_id,
        "section_path": result.chunk.section_path,
        "status": result.chunk.status.value,
        "access_level": result.chunk.access_level.value,
        "corpus_source": result.chunk.corpus_source.value,
        "text_preview": result.chunk.text[:200].replace("\n", " "),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview Week 2 retrieval results.")
    parser.add_argument("query")
    parser.add_argument("--mode", choices=["vector", "keyword", "hybrid"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--embedding-provider", default=None)
    parser.add_argument("--whoosh-index-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = run_search_preview(
            query=args.query,
            mode=args.mode,
            top_k=args.top_k,
            embedding_provider=args.embedding_provider,
            whoosh_index_dir=args.whoosh_index_dir,
        )
    except FileNotFoundError as exc:
        raise SystemExit(f"{exc}\n{REBUILD_HINT}") from exc
    except RuntimeError as exc:
        message = str(exc)
        if "Embedding provider guidance:" in message:
            raise SystemExit(message) from exc
        raise SystemExit(f"{message}\n{REBUILD_HINT}") from exc
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
