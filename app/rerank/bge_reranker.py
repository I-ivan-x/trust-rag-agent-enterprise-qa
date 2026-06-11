from __future__ import annotations

from app.core.config import get_settings
from app.core.enums import RetrievalSource
from app.schemas.retrieval import RetrievedChunk

DEFAULT_BGE_RERANKER_MODEL = "BAAI/bge-reranker-base"
MOCK_RERANKER_MODEL_NAME = "mock-reranker-v0"


class BGEReranker:
    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ) -> None:
        settings = get_settings()
        configured_model = model_name or settings.reranker_model_name
        self.model_name = configured_model or DEFAULT_BGE_RERANKER_MODEL
        if self.model_name == MOCK_RERANKER_MODEL_NAME:
            raise ValueError(
                "mock-reranker-v0 is only valid for RERANKER_PROVIDER=mock tests/smoke. "
                f"Use {DEFAULT_BGE_RERANKER_MODEL} for RERANKER_PROVIDER=bge."
            )
        self.device = device or settings.embedding_device
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for BGEReranker. "
                "Install the sentence-transformer optional dependency before using "
                "RERANKER_PROVIDER=bge."
            ) from exc

        try:
            self._model = CrossEncoder(self.model_name, device=self.device)
        except Exception as exc:
            raise RuntimeError(
                "BGE reranker model could not be loaded. "
                f"model={self.model_name} device={self.device} original_error={exc}"
            ) from exc

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks or top_n == 0:
            return []

        pairs = [(query, result.chunk.text) for result in chunks]
        try:
            raw_scores = self._model.predict(pairs, show_progress_bar=False)
        except Exception as exc:
            raise RuntimeError(
                "BGE reranker scoring failed. "
                f"model={self.model_name} candidate_count={len(chunks)} original_error={exc}"
            ) from exc

        scores = [float(score) for score in raw_scores]
        ranked = sorted(
            zip(scores, chunks, strict=True),
            key=lambda item: (-item[0], item[1].rank, item[1].chunk.chunk_id),
        )
        if top_n is not None:
            ranked = ranked[:top_n]

        return [
            result.model_copy(
                update={
                    "source": RetrievalSource.rerank,
                    "rerank_score": score,
                    "rank": rank,
                }
            )
            for rank, (score, result) in enumerate(ranked, start=1)
        ]
