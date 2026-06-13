from __future__ import annotations

from app.guards.evidence_gate import EvidenceGateConfig
from app.schemas.retrieval import RetrievalOptions
from app.workflow.orchestrator import run_trust_gated_pass
from tests.helpers import make_retrieved_chunk


def test_trust_gated_pass_uses_evidence_gate_config() -> None:
    chunk = make_retrieved_chunk(
        "chunk-rate-limit",
        "Refresh token rate limit.",
        rerank_score=0.1,
    )

    result = run_trust_gated_pass(
        query="refresh token rate limit",
        retrieval_options=RetrievalOptions(top_n_rerank=1),
        retriever=_FakeRetriever([chunk]),
        reranker=_FakeReranker(),
        user_role="employee",
        user_department="Engineering",
        user_clearance="internal",
        evidence_gate_config=EvidenceGateConfig(min_score=0.5),
    )

    assert result.evidence_decision.evidence_sufficient is False
    assert result.evidence_decision.reason == "top_score_below_minimum"


class _FakeRetriever:
    last_warnings: list[str] = []

    def __init__(self, chunks):
        self._chunks = chunks

    def retrieve(self, query, options):
        del query, options
        return self._chunks


class _FakeReranker:
    def rerank(self, query, chunks, top_n=None):
        del query
        return chunks[:top_n] if top_n is not None else chunks
