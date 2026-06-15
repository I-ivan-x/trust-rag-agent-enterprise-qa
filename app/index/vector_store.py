from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.enums import RetrievalSource
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


class VectorStore:
    def __init__(self, qdrant_url: str | None = None, collection_name: str | None = None) -> None:
        settings = get_settings()
        self.qdrant_url = qdrant_url or settings.qdrant_url
        self.collection_name = collection_name or settings.qdrant_collection
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise ImportError("qdrant-client is required for VectorStore") from exc
        self.client = _make_qdrant_client(QdrantClient, self.qdrant_url)

    def recreate_collection(self, vector_size: int) -> None:
        try:
            from qdrant_client.http import models

            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception as exc:
            _raise_qdrant_error("recreate collection", self.qdrant_url, self.collection_name, exc)

    def upsert_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        try:
            from qdrant_client.http import models

            points = [
                models.PointStruct(
                    id=_point_id(chunk.chunk_id),
                    vector=vector,
                    payload=chunk.model_dump(mode="json"),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
            if points:
                self.client.upsert(collection_name=self.collection_name, points=points)
        except Exception as exc:
            _raise_qdrant_error("upsert chunks", self.qdrant_url, self.collection_name, exc)

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        if top_k <= 0:
            return []
        try:
            query_filter = _build_qdrant_filter(filters)
            try:
                hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    query_filter=query_filter,
                    with_payload=True,
                )
            except AttributeError:
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=top_k,
                    query_filter=query_filter,
                    with_payload=True,
                )
                hits = response.points
        except Exception as exc:
            _raise_qdrant_error("search", self.qdrant_url, self.collection_name, exc)

        results: list[RetrievedChunk] = []
        for rank, hit in enumerate(hits, start=1):
            payload = dict(hit.payload or {})
            chunk = Chunk.model_validate(payload)
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    source=RetrievalSource.vector,
                    vector_score=float(hit.score),
                    rank=rank,
                )
            )
        return results

    def count(self) -> int:
        try:
            return int(self.client.count(collection_name=self.collection_name, exact=True).count)
        except Exception as exc:
            _raise_qdrant_error("count", self.qdrant_url, self.collection_name, exc)


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _make_qdrant_client(client_cls: Any, qdrant_url: str) -> Any:
    if qdrant_url == ":memory:":
        return client_cls(path=":memory:")
    if qdrant_url.startswith("local:"):
        local_path = qdrant_url.removeprefix("local:")
        if not local_path:
            raise ValueError("QDRANT_URL=local:<path> requires a non-empty path")
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        return client_cls(path=local_path)
    return client_cls(url=qdrant_url)


def _raise_qdrant_error(
    operation: str,
    qdrant_url: str,
    collection_name: str,
    exc: Exception,
) -> None:
    original_error = str(exc)
    category = _classify_qdrant_error(original_error)
    raise RuntimeError(
        "Qdrant "
        f"{operation} failed: {category}. "
        f"url={qdrant_url} collection={collection_name} original_error={original_error}"
    ) from exc


def _classify_qdrant_error(error_text: str) -> str:
    normalized = error_text.lower()
    if any(
        marker in normalized
        for marker in (
            "connection refused",
            "failed to connect",
            "max retries",
            "timed out",
            "timeout",
            "server disconnected",
            "failed to obtain server version",
            "actively refused",
            "unavailable",
        )
    ):
        return "qdrant service unavailable"
    if any(
        marker in normalized
        for marker in (
            "not found",
            "doesn't exist",
            "does not exist",
            "collection",
            "404",
        )
    ) and not any(marker in normalized for marker in ("dimension", "vector size")):
        return "collection not found or not built"
    if any(
        marker in normalized
        for marker in (
            "dimension",
            "vector size",
            "expected dim",
            "wrong input",
            "shape",
        )
    ):
        return "vector dimension mismatch"
    return "qdrant search error"


def _build_qdrant_filter(filters: dict[str, Any] | None) -> Any:
    if not filters:
        return None
    from qdrant_client.http import models

    conditions = []
    for key in ("status", "access_level", "corpus_source", "doc_id"):
        if key not in filters or filters[key] is None:
            continue
        value = filters[key]
        if isinstance(value, list):
            conditions.append(models.FieldCondition(key=key, match=models.MatchAny(any=value)))
        else:
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=conditions) if conditions else None
