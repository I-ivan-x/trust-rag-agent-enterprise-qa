import pytest

from app.index.vector_store import VectorStore


def test_vector_store_supports_local_memory_qdrant() -> None:
    store = VectorStore(qdrant_url=":memory:", collection_name="unit_test_vectors")

    store.recreate_collection(vector_size=2)

    assert store.count() == 0


def test_vector_store_search_error_includes_original_error_and_category() -> None:
    store = VectorStore.__new__(VectorStore)
    store.client = _DimensionMismatchClient()
    store.qdrant_url = "http://localhost:6333"
    store.collection_name = "trust_rag_enterprise_qa"

    with pytest.raises(RuntimeError) as exc_info:
        store.search([0.1] * 16, top_k=3)

    message = str(exc_info.value)
    assert "Qdrant search failed: vector dimension mismatch" in message
    assert (
        "original_error=Wrong input: Vector dimension error: expected dim: 384, got 16" in message
    )


class _DimensionMismatchClient:
    def search(self, **kwargs):
        raise ValueError("Wrong input: Vector dimension error: expected dim: 384, got 16")
