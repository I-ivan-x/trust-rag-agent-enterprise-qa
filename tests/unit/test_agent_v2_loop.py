from __future__ import annotations

from app.agent.actions import ActionProposal
from app.agent.diagnosis import ActionType
from app.agent.loop import run_agentic_v2_loop
from app.agent.validator import ActionBudget
from app.core.enums import AccessLevel, DocumentStatus
from app.eval.runner import run_eval
from app.rerank.reranker import MockReranker
from app.schemas.eval import EvalCase
from app.schemas.retrieval import RetrievalOptions
from tests.helpers import make_retrieved_chunk


def test_agentic_v2_cooccurrence_takes_b_then_answers() -> None:
    deprecated = make_retrieved_chunk(
        "deprecated",
        "old token limit",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
        doc_id="doc-old",
    )
    deprecated_2 = make_retrieved_chunk(
        "deprecated-2",
        "older token limit",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
        doc_id="doc-older",
    )
    clean = make_retrieved_chunk(
        "clean",
        "The active token limit is 30 requests per minute.",
        doc_id="doc-clean",
    )
    clean_hint = make_retrieved_chunk(
        "clean-hint",
        "The current rate ceiling is documented in the operations guide.",
        doc_id="doc-clean-hint",
    )
    retriever = _SequenceRetriever([[clean_hint, deprecated, deprecated_2], [clean]])

    result = run_agentic_v2_loop(
        case=_case(),
        retriever=retriever,
        reranker=MockReranker(),
        retrieval_options=RetrievalOptions(top_k_dense=0, top_k_sparse=5, top_n_rerank=5),
    )

    assert result.terminal_reason == "answer"
    assert result.budget_consumed == 1
    assert result.action_trajectory[0]["chosen_action"] == "filtered_retrieval"
    assert result.action_trajectory[0]["post_action_evidence_decision"] == "sufficient"
    assert result.action_trajectory[0]["action_outcome"] == "evidence_sufficient"
    assert result.action_trajectory[0]["budget_before"] == 0
    assert result.action_trajectory[0]["budget_after"] == 1
    assert result.trace_fields["agent_version"] == "v2"
    assert result.trace_fields["controller_source"] == "rule"
    assert result.trace_fields["action_sequence"] == ["filtered_retrieval"]
    assert result.trace_fields["action_outcomes"] == [
        {
            "step": 1,
            "action": "filtered_retrieval",
            "trigger": "POLICY_CROWDING",
            "outcome": "evidence_sufficient",
        }
    ]
    assert result.trace_fields["validator_rejections"] == []


def test_agentic_v2_budget_exhaustion_terminates_without_looping() -> None:
    weak = make_retrieved_chunk("weak", "unrelated", rerank_score=0.1)
    result = run_agentic_v2_loop(
        case=_case(),
        retriever=_SequenceRetriever([[weak]]),
        reranker=MockReranker(),
        retrieval_options=RetrievalOptions(top_k_dense=0, top_k_sparse=5, top_n_rerank=5),
        budget=ActionBudget(max_nonterminal_actions=0),
    )

    assert result.terminal_reason == "budget_exhausted"
    assert result.budget_consumed == 0
    assert result.action_trajectory[0]["validator_ok"] is False
    assert result.action_trajectory[0]["validator_reject_reason"] == "budget_exhausted"
    assert result.action_trajectory[0]["action_outcome"] == "validator_rejected"
    assert result.trace_fields["validator_rejections"] == [
        {
            "step": 1,
            "action": "rewrite_query",
            "reason": "budget_exhausted",
            "controller_source": "rule",
        }
    ]


def test_agentic_v2_validator_reject_is_traced() -> None:
    weak = make_retrieved_chunk("weak", "unrelated", rerank_score=0.1)
    result = run_agentic_v2_loop(
        case=_case(),
        retriever=_SequenceRetriever([[weak]]),
        reranker=MockReranker(),
        retrieval_options=RetrievalOptions(top_k_dense=0, top_k_sparse=5, top_n_rerank=5),
        controller=_IllegalController(),
    )

    assert result.terminal_reason == "refuse"
    assert result.action_trajectory[0]["chosen_action"] == "filtered_retrieval"
    assert result.action_trajectory[0]["validator_ok"] is False
    assert (
        result.action_trajectory[0]["validator_reject_reason"] == "action_not_legal_for_diagnosis"
    )
    assert result.trace_fields["action_sequence"] == ["filtered_retrieval"]


def test_agentic_v2_trace_fields_are_complete_on_terminal_refusal() -> None:
    restricted = make_retrieved_chunk(
        "restricted",
        "restricted admin key detail",
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
    )
    result = run_agentic_v2_loop(
        case=_case(),
        retriever=_SequenceRetriever([[restricted]]),
        reranker=MockReranker(),
        retrieval_options=RetrievalOptions(top_k_dense=0, top_k_sparse=5, top_n_rerank=5),
    )
    trace = result.trace_fields

    assert result.terminal_reason == "refuse"
    assert trace["agent_version"] == "v2"
    assert trace["controller_source"] == "rule"
    assert trace["budget_consumed"] == 0
    assert trace["terminal_reason"] == "refuse"
    assert trace["action_trajectory"][0]["diagnosis_failure_type"] == "PERMISSION_BLOCKED"
    assert trace["action_sequence"] == ["refuse_with_explanation"]
    assert trace["action_trajectory"][0]["action_outcome"] == "refuse"


def test_final_agentic_v2_can_run_through_eval_mock_path(tmp_path) -> None:
    summary = run_eval(
        split="fixture",
        systems=["final_agentic_v2"],
        mock_run=True,
        output_root=tmp_path,
        run_id="agent-v2-mock",
        write_reports=False,
        limit=1,
    )

    assert summary["systems"] == ["final_agentic_v2"]
    assert summary["mode"] == "mock_smoke"
    assert summary["llm_call_count"] == 0


def _case() -> EvalCase:
    return EvalCase(
        case_id="agent-v2-case",
        split="fixture",
        query="What is the active token limit?",
        query_type="single_doc_fact",
        expected_behavior="answer",
        gold_doc_ids=["doc-clean"],
        gold_chunk_ids=["clean"],
        reference_claims=["The active token limit is 30 requests per minute."],
    )


class _SequenceRetriever:
    def __init__(self, batches) -> None:
        self.batches = list(batches)
        self.calls = 0
        self.last_warnings = []

    def retrieve(self, query, options, filters=None):
        del query, options
        index = min(self.calls, len(self.batches) - 1)
        self.calls += 1
        results = self.batches[index]
        if filters and filters.get("exclude_doc_ids"):
            excluded = set(filters["exclude_doc_ids"])
            results = [item for item in results if item.chunk.doc_id not in excluded]
        if filters and filters.get("status") == "active":
            results = [item for item in results if item.chunk.status == DocumentStatus.active]
        return results


class _IllegalController:
    def select(self, diagnosis, context=None):
        del diagnosis, context
        return ActionProposal(
            action=ActionType.filtered_retrieval,
            args={"filters": {"status": "active"}},
            source="rule",
        )
