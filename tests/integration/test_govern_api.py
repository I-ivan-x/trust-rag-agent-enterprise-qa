from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import govern_routes
from app.core.enums import AccessLevel, RetrievalSource
from app.govern.conditions import GovernanceAction, OpsCondition, RiskTier
from app.govern.sinks import LocalJsonlSink
from app.main import create_app
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


def test_govern_run_returns_outcome(tmp_path: Path) -> None:
    client = _client(tmp_path, _config_violation_chunks())

    response = client.post(
        "/govern/run",
        json={
            "query": "restricted namespace privileged pod remediation ticket",
            "user_role": "admin",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    result = payload["result"]
    trace = payload["trace"]
    assert result["detected_conditions"] == ["CONFIG_VIOLATION"]
    assert result["proposed_action"] == "open_remediation_ticket"
    assert result["validator_ok"] is True
    assert result["approval_state"] == "pending_approval"
    assert result["executed_side_effect"] is False
    assert trace["governance_trace"]["validator_verdict"] == "accepted"


def test_govern_run_unauthorized_blocked(tmp_path: Path) -> None:
    client = _client(tmp_path, _config_violation_chunks())

    response = client.post(
        "/govern/run",
        json={
            "query": "给 privileged pod 违规开一张整改工单",
            "user_role": "viewer",
        },
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["detected_conditions"][0] == "PERMISSION_BLOCKED"
    assert result["authorized_actor"] is False
    assert result["proposed_action"] == "escalate_to_human"
    assert result["approval_state"] == "escalated"
    assert result["executed_side_effect"] is False


def test_pending_list_then_approve(tmp_path: Path) -> None:
    client = _client(tmp_path, _config_violation_chunks())
    run = client.post(
        "/govern/run",
        json={
            "query": "restricted namespace privileged pod remediation ticket",
            "user_role": "admin",
        },
    )
    record_id = run.json()["result"]["sink_record_id"]

    pending = client.get("/govern/pending")
    assert pending.status_code == 200
    assert [record["record_id"] for record in pending.json()] == [record_id]

    approved = client.post(f"/govern/pending/{record_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["approval_state"] == "committed"
    assert client.get("/govern/pending").json() == []


def test_pending_reject_drops(tmp_path: Path) -> None:
    client = _client(tmp_path, _config_violation_chunks())
    run = client.post(
        "/govern/run",
        json={
            "query": "restricted namespace privileged pod remediation ticket",
            "user_role": "admin",
        },
    )
    record_id = run.json()["result"]["sink_record_id"]

    rejected = client.post(f"/govern/pending/{record_id}/reject")

    assert rejected.status_code == 200
    assert rejected.json()["approval_state"] == "dropped"
    assert client.get("/govern/pending").json() == []


def test_approve_on_committed_4xx(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path / "action_store")
    record = sink.record_action(
        action=GovernanceAction.open_remediation_ticket,
        condition=OpsCondition.config_violation,
        doc_ids=["doc-policy"],
        evidence_citations=["doc-policy::chunk-0000"],
        actor_role="admin",
        risk_tier=RiskTier.approval,
        approval_state="committed",
    )
    client = _client(tmp_path, _config_violation_chunks(), sink=sink)

    response = client.post(f"/govern/pending/{record.record_id}/approve")

    assert 400 <= response.status_code < 500


def test_audit_blocked_filter(tmp_path: Path) -> None:
    client = _client(tmp_path, _config_violation_chunks())
    run = client.post(
        "/govern/run",
        json={
            "query": "给 privileged pod 违规开一张整改工单",
            "user_role": "viewer",
        },
    )
    record_id = run.json()["result"]["sink_record_id"]

    audit = client.get("/govern/audit")
    blocked = client.get("/govern/audit/blocked")

    assert audit.status_code == 200
    assert blocked.status_code == 200
    assert record_id in {record["record_id"] for record in audit.json()}
    assert [record["record_id"] for record in blocked.json()] == [record_id]


def test_audit_blocked_includes_forced_escalation(tmp_path: Path) -> None:
    sink = LocalJsonlSink(tmp_path / "action_store")
    record = sink.record_action(
        action=GovernanceAction.escalate_to_human,
        condition=OpsCondition.config_violation,
        doc_ids=["doc-policy"],
        evidence_citations=["doc-policy::chunk-0000"],
        actor_role="admin",
        risk_tier=RiskTier.terminal,
        approval_state="escalated",
    )
    client = _client(tmp_path, _config_violation_chunks(), sink=sink)

    blocked = client.get("/govern/audit/blocked")

    assert blocked.status_code == 200
    assert [item["record_id"] for item in blocked.json()] == [record.record_id]


def _client(
    tmp_path: Path,
    chunks: list[RetrievedChunk],
    *,
    sink: LocalJsonlSink | None = None,
) -> TestClient:
    app = create_app()
    resolved_sink = sink or LocalJsonlSink(tmp_path / "action_store")
    app.dependency_overrides[govern_routes.get_govern_sink] = lambda: resolved_sink
    app.dependency_overrides[govern_routes.get_govern_retriever] = lambda: _StubRetriever(
        chunks
    )
    app.dependency_overrides[govern_routes.get_govern_reranker] = lambda: _IdentityReranker()
    return TestClient(app)


class _StubRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.last_warnings: list[str] = []

    def retrieve(self, query, options=None, filters=None):  # noqa: ANN001
        del query, options, filters
        return self.chunks


class _IdentityReranker:
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        del query
        return chunks[:top_n] if top_n is not None else chunks


def _config_violation_chunks() -> list[RetrievedChunk]:
    return [
        _retrieved(
            Chunk(
                chunk_id="policy-restricted-pod-security::chunk-0000",
                doc_id="policy-restricted-pod-security",
                chunk_index=0,
                text="restricted namespace privileged pod remediation ticket policy",
                section_path=["Policy"],
                token_count=8,
                char_count=64,
                version="test",
                access_level=AccessLevel.restricted,
                allowed_roles=["admin"],
            ),
            1,
        ),
        _retrieved(
            Chunk(
                chunk_id="sop-pod-security-violations::chunk-0000",
                doc_id="sop-pod-security-violations",
                chunk_index=0,
                text="privileged pod remediation ticket violation evidence",
                section_path=["Violation"],
                token_count=7,
                char_count=56,
                version="test",
                access_level=AccessLevel.restricted,
                allowed_roles=["admin"],
                policy_ref="policy-restricted-pod-security",
                overlay_relation_note={"type": "violates_policy"},
            ),
            2,
        ),
    ]


def _retrieved(chunk: Chunk, rank: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=chunk,
        source=RetrievalSource.hybrid,
        rank=rank,
        rrf_score=1.0 / rank,
    )
