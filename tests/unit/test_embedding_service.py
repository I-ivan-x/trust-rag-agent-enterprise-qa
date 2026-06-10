import pytest

from app.index.embedding_service import (
    MockEmbeddingService,
    OpenAICompatibleEmbeddingService,
    SentenceTransformerEmbeddingService,
)


def test_mock_embedding_is_deterministic() -> None:
    service = MockEmbeddingService()

    first = service.embed_texts(["refresh token"])
    second = service.embed_texts(["refresh token"])

    assert first == second
    assert len(first[0]) == 16


def test_mock_embedding_differs_for_different_text() -> None:
    service = MockEmbeddingService()

    assert service.embed_query("refresh token") != service.embed_query("admin key")


def test_mock_embedding_rejects_empty_text() -> None:
    service = MockEmbeddingService()

    with pytest.raises(ValueError, match="empty text"):
        service.embed_texts([""])


def test_sentence_transformer_service_can_be_constructed_or_skipped() -> None:
    try:
        service = SentenceTransformerEmbeddingService(model_name="BAAI/bge-small-en-v1.5")
    except Exception as exc:
        pytest.skip(f"sentence-transformer model unavailable in this environment: {exc}")

    vector = service.embed_query("refresh token rate limit")
    assert vector
    assert isinstance(vector[0], float)


def test_openai_compatible_embedding_requires_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAICompatibleEmbeddingService(api_key="")

