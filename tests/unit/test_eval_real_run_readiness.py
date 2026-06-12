from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.enums import ExpectedBehavior, QueryType
from app.eval import runner
from app.schemas.eval import EvalCase


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def _case() -> EvalCase:
    return EvalCase(
        case_id="case-secret-001",
        query="What is the token ttl?",
        query_type=QueryType.single_doc_fact,
        expected_behavior=ExpectedBehavior.answer,
        expected_rewrite="FORBIDDEN_REWRITE_VALUE",
        gold_doc_ids=["FORBIDDEN_GOLD_DOC"],
        gold_chunk_ids=["FORBIDDEN_GOLD_CHUNK"],
        reference_answer="FORBIDDEN_REFERENCE_ANSWER",
        reference_claims=["FORBIDDEN_REFERENCE_CLAIM"],
    )


def test_real_ready_rejects_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "get_settings", lambda: _settings(llm_provider="mock"))
    with pytest.raises(RuntimeError, match="LLM_PROVIDER=mock"):
        runner._require_real_run_ready(["final_gated"])


def test_real_ready_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner,
        "get_settings",
        lambda: _settings(llm_provider="deepseek", deepseek_api_key=None),
    )
    with pytest.raises(RuntimeError, match="requires an API key"):
        runner._require_real_run_ready(["direct_llm"])


def test_direct_llm_requires_real_run() -> None:
    with pytest.raises(ValueError, match="direct_llm"):
        runner._validate_mode(
            ["direct_llm"], mock_run=True, retrieval_only=False, real_run=False
        )


def test_offline_final_never_simulates_outside_mock_run() -> None:
    # Guard: the simulated headline path is reachable only under --mock-run.
    with pytest.raises(RuntimeError, match="_simulate_final_response"):
        runner._run_case_offline(
            _case(),
            "final_gated",
            [],
            retrieval_only=False,
            mock_run=False,
        )


def test_raw_correct_scoring_for_refusal_matches_expected() -> None:
    from app.eval.real_pipeline import RealFinalResult

    case = EvalCase(
        case_id="case-refuse",
        query="secret roadmap?",
        query_type=QueryType.no_evidence,
        expected_behavior=ExpectedBehavior.refuse_no_evidence,
    )
    refused = RealFinalResult(
        reranked_chunks=[],
        first_pass_reranked=None,
        refused=True,
        decision_reason=runner.DecisionReason.no_evidence,
        response_mode=ExpectedBehavior.refuse_no_evidence,
        citations=[],
        answer_text="I do not have enough provided evidence to answer this question.",
        rewrite_source="none",
        actual_rewritten_query=None,
        rewrite_model_name=None,
        rewrite_reason=None,
        second_pass_attempted=False,
        reranker_unavailable=False,
    )
    assert runner._score_raw_correct(case, refused) is True
