from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.enums import AccessLevel, DocumentStatus, RetrievalSource
from app.llm.mock_llm import MockLLMClient
from app.main import create_app
from tests.helpers import make_retrieved_chunk


def test_rate_limit_query_returns_answer_with_real_chunk(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/chat",
        json=_request("What is the refresh token rate limit in Auth Service API v2?"),
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["response_mode"] == "answer"
    assert payload["citations"][0]["chunk_id"] == "doc-api-auth-service-v2::chunk-0002"
    assert payload["decision"]["final_response_mode"] == "answer"
    assert "trust_trace" in payload


def test_restricted_admin_key_query_by_employee_refuses_permission(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post("/chat", json=_request("How often must admin keys be rotated?"))

    payload = response.json()
    assert payload["response_mode"] == "refuse_permission"
    assert payload["citations"] == []
    assert "90 days" not in payload["answer"]
    assert payload["retrieved_chunks_preview"] == []
    assert payload["trust_trace"]["acl_blocked_count"] == 1


def test_deprecated_v1_lifetime_query_warns_deprecated(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post("/chat", json=_request("What was the v1 access token lifetime?"))

    payload = response.json()
    assert payload["response_mode"] == "warn_deprecated"
    assert "deprecated" in payload["answer"].lower()
    assert payload["citations"][0]["chunk_id"] == "doc-api-auth-service-v1::chunk-0000"


def test_active_active_token_lifetime_conflict_reports_conflict(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/chat",
        json=_request("What is the access token lifetime during the v2 migration?"),
    )

    payload = response.json()
    assert payload["response_mode"] == "report_conflict"
    assert "conflicting active document evidence" in payload["answer"]
    assert {citation["doc_id"] for citation in payload["citations"]} == {
        "doc-api-auth-service-v2",
        "doc-meeting-auth-token-lifetime-decision",
    }
    assert payload["trust_trace"]["conflict_detected"] is True


def test_unknown_query_refuses_no_evidence(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post("/chat", json=_request("How do I configure Kubernetes autoscaling?"))

    payload = response.json()
    assert payload["response_mode"] == "refuse_no_evidence"
    assert payload["citations"] == []
    assert "not have enough" in payload["answer"]


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
        if "v1" in lower:
            return [_deprecated_v1_chunk(), _active_access_token_chunk()]
        if "during the v2 migration" in lower:
            return [_active_access_token_chunk(), _meeting_conflict_chunk()]
        if "refresh token rate limit" in lower or "rate limit" in lower:
            return [_rate_limit_chunk()]
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


def _rate_limit_chunk():
    return make_retrieved_chunk(
        "doc-api-auth-service-v2::chunk-0002",
        "The refresh token endpoint is limited to 30 requests per minute per client.",
        doc_id="doc-api-auth-service-v2",
        section_path=["Auth Service API v2", "Refresh Token Rate Limit"],
        rank=1,
    )


def _active_access_token_chunk():
    return make_retrieved_chunk(
        "doc-api-auth-service-v2::chunk-0000",
        "In v2 the access token lifetime is 30 minutes.",
        doc_id="doc-api-auth-service-v2",
        section_path=["Auth Service API v2", "Access Token Lifetime"],
        conflict_group_id="auth-token-lifetime",
        rank=1,
    )


def _deprecated_v1_chunk():
    return make_retrieved_chunk(
        "doc-api-auth-service-v1::chunk-0000",
        "In v1 the access token lifetime was 60 minutes.",
        doc_id="doc-api-auth-service-v1",
        section_path=["Auth Service API v1", "Access Token Lifetime"],
        status=DocumentStatus.deprecated,
        conflict_group_id="auth-token-lifetime",
        rank=1,
    )


def _meeting_conflict_chunk():
    return make_retrieved_chunk(
        "doc-meeting-auth-token-lifetime-decision::chunk-0000",
        "The team agreed to keep the access token lifetime at 60 minutes.",
        doc_id="doc-meeting-auth-token-lifetime-decision",
        section_path=["Auth Token Lifetime Decision Notes", "Decision"],
        conflict_group_id="auth-token-lifetime",
        rank=2,
    )


def _admin_key_chunk():
    return make_retrieved_chunk(
        "doc-security-admin-key-rotation-sop::chunk-0000",
        "Admin keys must be rotated every 90 days by a security administrator.",
        doc_id="doc-security-admin-key-rotation-sop",
        section_path=["Admin Key Rotation SOP", "Restricted Procedure"],
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
        rank=1,
    )
