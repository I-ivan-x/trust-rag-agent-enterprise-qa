from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.enums import AccessLevel, DocumentStatus, RetrievalSource
from app.llm.mock_llm import MockLLMClient
from app.main import create_app
from app.rerank.reranker import MockReranker
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


def test_chat_api_returns_answer_with_citation(monkeypatch) -> None:
    class FakeRetriever:
        last_warnings: list[str] = []

        def retrieve(self, query, options=None, filters=None):
            return [_retrieved_auth_rate_limit_chunk()]

    monkeypatch.setattr(
        "app.service.chat_service._make_hybrid_retriever",
        lambda: FakeRetriever(),
    )
    monkeypatch.setattr(
        "app.service.chat_service.get_reranker",
        lambda provider=None: MockReranker(),
    )
    monkeypatch.setattr(
        "app.service.chat_service.get_llm_client",
        lambda provider=None: MockLLMClient(),
    )

    client = TestClient(create_app())
    response = client.post(
        "/chat",
        json={
            "query": "What is the refresh token rate limit in Auth Service API v2?",
            "user_role": "employee",
            "user_department": "Engineering",
            "user_clearance": "internal",
            "retrieval_options": {
                "top_k": 8,
                "top_n_rerank": 4,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "30 requests per minute" in payload["answer"]
    assert payload["response_mode"] == "answer"
    assert payload["trace_id"]
    assert payload["citations"]
    assert payload["citations"][0]["chunk_id"] == "doc-api-auth-service-v2::chunk-0002"
    assert payload["provider_metadata"]["llm_provider"] == "mock"
    assert payload["provider_metadata"]["mock_llm_for_local_demo_only"] is True
    assert any("MockLLMClient" in warning for warning in payload["warnings"])


def _retrieved_auth_rate_limit_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id="doc-api-auth-service-v2::chunk-0002",
            doc_id="doc-api-auth-service-v2",
            chunk_index=2,
            text=(
                "The refresh token endpoint is limited to 30 requests per minute per "
                "client. Requests above this limit receive an HTTP 429 response."
            ),
            section_path=["Auth Service API v2", "Refresh Token Rate Limit"],
            token_count=24,
            char_count=131,
            line_start=45,
            line_end=46,
            status=DocumentStatus.active,
            version="v2",
            allowed_roles=["employee", "engineer"],
            access_level=AccessLevel.internal,
        ),
        source=RetrievalSource.hybrid,
        rrf_score=0.1,
        rank=1,
    )
