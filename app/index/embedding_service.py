from __future__ import annotations

import hashlib
from typing import Protocol

from app.core.config import get_settings


class BaseEmbeddingService(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, query: str) -> list[float]:
        ...


class MockEmbeddingService:
    """Deterministic smoke-test embeddings; never use for formal retrieval eval conclusions."""

    def __init__(self, dimension: int = 16) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if any(not text.strip() for text in texts):
            raise ValueError("MockEmbeddingService does not accept empty text")
        return [self._embed_one(text) for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]

    def _embed_one(self, text: str) -> list[float]:
        values: list[float] = []
        for index in range(self.dimension):
            digest = hashlib.sha256(f"{index}:{text}".encode()).digest()
            integer = int.from_bytes(digest[:8], byteorder="big", signed=False)
            values.append((integer / ((1 << 64) - 1)) * 2 - 1)
        return values


class SentenceTransformerEmbeddingService:
    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int | None = None,
        device: str | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model_name
        self.batch_size = batch_size or settings.embedding_batch_size
        self.device = device or settings.embedding_device
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed. Install the optional "
                "sentence-transformer dependency before using this provider."
            ) from exc
        self._model = SentenceTransformer(self.model_name, device=self.device)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise ValueError("SentenceTransformerEmbeddingService does not accept empty text")
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.astype(float).tolist()

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]


class OpenAICompatibleEmbeddingService:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.base_url = base_url if base_url is not None else settings.openai_base_url
        self.model_name = model_name or settings.embedding_model_name
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI-compatible embeddings")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("OpenAI-compatible embedding calls are a Week 2 interface stub")

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]


def get_embedding_service(provider: str | None = None) -> BaseEmbeddingService:
    settings = get_settings()
    selected_provider = (provider or settings.embedding_provider).lower()
    if selected_provider == "mock":
        return MockEmbeddingService()
    if selected_provider in {"sentence_transformer", "sentence-transformer"}:
        return SentenceTransformerEmbeddingService()
    if selected_provider in {"openai", "openai_compatible", "openai-compatible"}:
        return OpenAICompatibleEmbeddingService()
    raise ValueError(f"Unsupported embedding provider: {selected_provider}")
