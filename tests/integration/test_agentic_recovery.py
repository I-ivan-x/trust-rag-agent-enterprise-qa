from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.enums import AccessLevel, RetrievalSource
from app.llm.mock_llm import MockLLMClient
from app.main import create_app
from tests.helpers import make_retrieved_chunk


def test_obfuscated_query_records_rewrite_and_answers(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post("/chat", json=_request("token ttl"))

    payload = response.json()
    assert payload["response_mode"] == "answer"
    assert payload["trust_trace"]["rewrite_triggered"] is True
    assert payload["trust_trace"]["retrieval_pass_count"] == 2
    assert payload["decision"]["rewritten_query"] == "access token lifetime"
    assert payload["citations"][0]["chunk_id"] == "doc-api-auth-service-v2::chunk-0000"


def test_rewrite_does_not_bypass_acl(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post("/chat", json=_request("admin key rotation ttl"))

    payload = response.json()
    assert payload["response_mode"] == "refuse_permission"
    assert payload["trust_trace"]["rewrite_triggered"] is False
    assert payload["trust_trace"]["retrieval_pass_count"] == 1
    assert "90 days" not in payload["answer"]


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(
        "app.service.chat_service._make_hybrid_retriever",
        lambda: _FakeRetriever(),
    )
    monkeypatch.setattr(
        "app.service.chat_service.get_reranker",
        lambda provider=None: _FakeReranker(),
    )
    monkeypatch.setattr(
        "app.service.chat_service.get_llm_client",
        lambda provider=None: MockLLMClient(),
    )
    return TestClient(create_app())


def _request(query: str) -> dict:
    return {
        "query": query,
        "user_role": "employee",
        "user_department": "Engineering",
        "user_clearance": "internal",
        "retrieval_options": {"top_k": 8, "top_n_rerank": 4},
    }


class _FakeRetriever:
    last_warnings: list[str] = []

    def retrieve(self, query, options=None, filters=None):
        lower = query.lower()
        if "admin key" in lower:
            return [_admin_key_chunk()]
        if "token ttl" in lower:
            return [
                make_retrieved_chunk(
                    "doc-deployment-rollout-guide::chunk-0000",
                    "Deployment rings use a staged rollout.",
                    doc_id="doc-deployment-rollout-guide",
                    section_path=["Deployment Rollout Guide", "Rings"],
                )
            ]
        if "access token lifetime" in lower:
            return [_active_access_token_chunk()]
        return []


class _FakeReranker:
    def rerank(self, query, chunks, top_n=None):
        ranked = [
            result.model_copy(
                update={
                    "source": RetrievalSource.rerank,
                    "rerank_score": result.rerank_score or 0.9 - index * 0.1,
                    "rank": index + 1,
                }
            )
            for index, result in enumerate(chunks)
        ]
        return ranked[:top_n] if top_n is not None else ranked


def _active_access_token_chunk():
    return make_retrieved_chunk(
        "doc-api-auth-service-v2::chunk-0000",
        "In v2 the access token lifetime is 30 minutes.",
        doc_id="doc-api-auth-service-v2",
        section_path=["Auth Service API v2", "Access Token Lifetime"],
    )


def _admin_key_chunk():
    return make_retrieved_chunk(
        "doc-security-admin-key-rotation-sop::chunk-0000",
        "Admin keys must be rotated every 90 days by a security administrator.",
        doc_id="doc-security-admin-key-rotation-sop",
        section_path=["Admin Key Rotation SOP", "Restricted Procedure"],
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
    )
