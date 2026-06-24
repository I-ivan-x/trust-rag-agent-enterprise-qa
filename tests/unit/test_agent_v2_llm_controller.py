from __future__ import annotations

import json
from typing import Any

from app.agent.controller import ControllerContext, RuleController
from app.agent.diagnosis import ActionType, DiagnosisReport, FailureType
from app.agent.llm_controller import LLMController
from app.agent.loop import run_agentic_v2_loop
from app.core.enums import DocumentStatus
from app.eval.runner import run_eval
from app.rerank.reranker import MockReranker
from app.schemas.eval import EvalCase
from app.schemas.retrieval import RetrievalOptions
from tests.helpers import make_retrieved_chunk


def test_llm_controller_valid_action_is_accepted_and_traced() -> None:
    deprecated = make_retrieved_chunk(
        "old",
        "old token limit",
        doc_id="doc-old",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )
    deprecated_2 = make_retrieved_chunk(
        "older",
        "older token limit",
        doc_id="doc-older",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
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
    llm = _FakeControllerLLM(
        {
            "action": "filtered_retrieval",
            "args": {"filters": {"status": "active"}},
            "reason": "Use active documents only.",
        }
    )

    result = run_agentic_v2_loop(
        case=_case(),
        retriever=_SequenceRetriever([[clean_hint, deprecated, deprecated_2], [clean]]),
        reranker=MockReranker(),
        retrieval_options=_options(),
        controller=LLMController(llm),
    )

    row = result.action_trajectory[0]
    assert result.terminal_reason == "answer"
    assert result.trace_fields["controller_source"] == "llm"
    assert row["controller_source"] == "llm"
    assert row["chosen_source"] == "llm"
    assert row["accepted"] is True
    assert row["fallback_reason"] is None
    assert row["llm_raw_proposal"]["action"] == "filtered_retrieval"
    assert llm.temperatures == [0]


def test_llm_controller_bad_json_parse_falls_back_to_rule() -> None:
    diagnosis = _diag(
        FailureType.policy_crowding,
        [ActionType.filtered_retrieval, ActionType.refuse_with_explanation],
    )
    proposal = LLMController(_FakeControllerLLM("not-json")).select(
        diagnosis,
        ControllerContext(query="token limit", neighborhood=[]),
    )

    assert proposal.action == ActionType.filtered_retrieval
    assert proposal.source == "llm_fallback_rule"
    assert proposal.accepted is False
    assert proposal.fallback_reason == "parse_error"
    assert proposal.llm_raw_proposal is None


def test_llm_action_not_legal_is_validator_rejected_then_rule_fallback() -> None:
    weak = make_retrieved_chunk("weak", "unrelated", rerank_score=0.1)
    llm = _FakeControllerLLM(
        {
            "action": "filtered_retrieval",
            "args": {"filters": {"status": "active"}},
            "reason": "Try filtering first.",
        }
    )

    result = run_agentic_v2_loop(
        case=_case(),
        retriever=_SequenceRetriever([[weak], [weak]]),
        reranker=MockReranker(),
        retrieval_options=_options(),
        controller=LLMController(llm),
        max_steps=1,
    )

    row = result.action_trajectory[0]
    assert row["chosen_action"] == "rewrite_query"
    assert row["chosen_source"] == "llm_fallback_rule"
    assert row["accepted"] is False
    assert row["fallback_reason"] == "validator_reject:action_not_legal_for_diagnosis"
    assert row["llm_raw_proposal"]["action"] == "filtered_retrieval"


def test_llm_filter_widening_is_validator_rejected_then_rule_fallback() -> None:
    deprecated = make_retrieved_chunk(
        "old",
        "old token limit",
        doc_id="doc-old",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )
    deprecated_2 = make_retrieved_chunk(
        "older",
        "older token limit",
        doc_id="doc-older",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )
    clean_hint = make_retrieved_chunk(
        "clean-hint",
        "The current rate ceiling is documented in the operations guide.",
        doc_id="doc-clean-hint",
    )
    llm = _FakeControllerLLM(
        {
            "action": "filtered_retrieval",
            "args": {"filters": {"status": "deprecated"}},
            "reason": "Look at deprecated documents.",
        }
    )

    result = run_agentic_v2_loop(
        case=_case(),
        retriever=_SequenceRetriever([[clean_hint, deprecated, deprecated_2], []]),
        reranker=MockReranker(),
        retrieval_options=_options(),
        controller=LLMController(llm),
        max_steps=1,
    )

    row = result.action_trajectory[0]
    assert row["chosen_action"] == "filtered_retrieval"
    assert row["chosen_source"] == "llm_fallback_rule"
    assert row["fallback_reason"] == "validator_reject:status_filter_must_only_allow_active"


def test_llm_rewrite_new_entity_is_validator_rejected_then_rule_fallback() -> None:
    weak = make_retrieved_chunk("weak", "refresh token rate limit", rerank_score=0.1)
    llm = _FakeControllerLLM(
        {
            "action": "rewrite_query",
            "args": {"rewritten_query": "secret payroll export"},
            "reason": "Bad rewrite with new entities.",
        }
    )

    result = run_agentic_v2_loop(
        case=_case(query="refresh rlimit for auth?"),
        retriever=_SequenceRetriever([[weak], [weak]]),
        reranker=MockReranker(),
        retrieval_options=_options(),
        controller=LLMController(llm),
        max_steps=1,
    )

    row = result.action_trajectory[0]
    assert row["chosen_action"] == "rewrite_query"
    assert row["chosen_source"] == "llm_fallback_rule"
    assert row["fallback_reason"].startswith(
        "validator_reject:rewrite_entities_not_allowed:"
    )


def test_llm_controller_always_illegal_degrades_to_rule_actions() -> None:
    deprecated = make_retrieved_chunk(
        "old",
        "old token limit",
        doc_id="doc-old",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )
    deprecated_2 = make_retrieved_chunk(
        "older",
        "older token limit",
        doc_id="doc-older",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )

    rule_result = run_agentic_v2_loop(
        case=_case(),
        retriever=_SequenceRetriever([[deprecated, deprecated_2], []]),
        reranker=MockReranker(),
        retrieval_options=_options(),
        max_steps=1,
    )
    llm_result = run_agentic_v2_loop(
        case=_case(),
        retriever=_SequenceRetriever([[deprecated, deprecated_2], []]),
        reranker=MockReranker(),
        retrieval_options=_options(),
        controller=LLMController(
            _FakeControllerLLM(
                {"action": "exfiltrate", "args": {}, "reason": "Never legal."}
            )
        ),
        max_steps=1,
    )

    rule_actions = [row["chosen_action"] for row in rule_result.action_trajectory]
    llm_actions = [row["chosen_action"] for row in llm_result.action_trajectory]
    assert llm_actions == rule_actions
    assert llm_result.action_trajectory[0]["chosen_source"] == "llm_fallback_rule"


def test_rule_controller_ignores_context_regression() -> None:
    diagnosis = _diag(
        FailureType.policy_crowding,
        [
            ActionType.rewrite_query,
            ActionType.filtered_retrieval,
            ActionType.refuse_with_explanation,
        ],
    )
    controller = RuleController()

    first = controller.select(
        diagnosis,
        ControllerContext(query="one", neighborhood=[{"doc_id": "doc-a"}]),
    )
    second = controller.select(
        diagnosis,
        ControllerContext(query="two", neighborhood=[{"doc_id": "doc-b"}]),
    )

    assert first.action == second.action == ActionType.filtered_retrieval
    assert first.source == second.source == "rule"


def test_final_agentic_v2_llm_can_run_through_eval_mock_path(tmp_path) -> None:
    summary = run_eval(
        split="fixture",
        systems=["final_agentic_v2_llm"],
        mock_run=True,
        output_root=tmp_path,
        run_id="agent-v2-llm-mock",
        write_reports=False,
        limit=1,
    )

    assert summary["systems"] == ["final_agentic_v2_llm"]
    assert summary["mode"] == "mock_smoke"
    assert summary["llm_call_count"] == 0


def test_q1_final_agentic_mock_path_still_uses_existing_rewrite_policy(tmp_path) -> None:
    summary = run_eval(
        split="fixture",
        systems=["final_agentic"],
        mock_run=True,
        output_root=tmp_path,
        run_id="agent-q1-mock",
        write_reports=False,
        limit=1,
    )

    assert summary["systems"] == ["final_agentic"]
    assert summary["mode"] == "mock_smoke"
    assert summary["llm_call_count"] == 0


def _case(
    *,
    query: str = "What is the active token limit?",
) -> EvalCase:
    return EvalCase(
        case_id="agent-v2-llm-case",
        split="fixture",
        query=query,
        query_type="single_doc_fact",
        expected_behavior="answer",
        gold_doc_ids=["doc-clean"],
        gold_chunk_ids=["clean"],
        reference_claims=["The active token limit is 30 requests per minute."],
    )


def _diag(failure_type: FailureType, legal_actions: list[ActionType]) -> DiagnosisReport:
    return DiagnosisReport(
        evidence_decision="insufficient",
        permission_blocked_count=0,
        deprecated_neighbor_count=2,
        restricted_neighbor_count=0,
        conflict_group_ids=[],
        clean_active_count=0,
        top_rerank_score=0.1,
        support_chunk_count=0,
        entity_miss=True,
        failure_type=failure_type,
        legal_actions=legal_actions,
    )


def _options() -> RetrievalOptions:
    return RetrievalOptions(top_k_dense=0, top_k_sparse=5, top_n_rerank=5)


class _SequenceRetriever:
    def __init__(self, batches: list[list[Any]]) -> None:
        self.batches = list(batches)
        self.calls = 0
        self.last_warnings: list[str] = []

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


class _FakeControllerLLM:
    def __init__(self, *responses: dict[str, Any] | str) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.prompts: list[str] = []
        self.temperatures: list[float | int | None] = []

    def generate(self, prompt: str, *, temperature: float | int | None = None) -> str:
        self.prompts.append(prompt)
        self.temperatures.append(temperature)
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        response = self.responses[index]
        if isinstance(response, str):
            return response
        return json.dumps(response)
