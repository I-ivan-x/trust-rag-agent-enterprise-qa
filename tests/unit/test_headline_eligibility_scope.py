from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import app.eval.runner as runner
from app.core.enums import EvalSplit
from app.llm.usage import LLMUsageTotals
from app.schemas.eval import EvalResult


def _result() -> EvalResult:
    return EvalResult(
        case_id="case-1",
        system_name="final_gated",
        eval_split=EvalSplit.external,
        corpus_source="public_external",
        raw_correct=True,
        grounded_correct=True,
        citation_valid=True,
        refused=False,
        metrics={"grounded_correct": True, "citation_valid": True},
    )


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider="deepseek",
        llm_model_name="deepseek-v4-flash",
        rewrite_llm_provider="rule_based",
        rewrite_llm_model_name="deepseek-v4-flash",
        reranker_provider="bge",
    )


def test_pilot_real_run_cannot_be_headline(monkeypatch) -> None:
    monkeypatch.setattr(runner, "get_settings", _settings)
    summary = runner._build_summary(
        run_id="pilot",
        systems=["final_gated"],
        eval_split=EvalSplit.external,
        cases=[],
        results=[_result()],
        trace_rows=[{"trace_id": "t"}],
        audit_rows=[{"case_id": "case-1"}],
        unavailable_systems={},
        full_case_count=50,
        case_selection={"limit": 1, "case_id": None, "max_cases": None},
        mock_run=False,
        retrieval_only=False,
        real_run=True,
        reranker_unavailable_any=True,
        run_dir=Path("data/eval_runs/pilot"),
        usage=LLMUsageTotals(answer_calls=1, total_tokens=100, usage_reported=True),
    )

    assert summary["headline_eligible"] is False
    assert summary["headline_scope"] == "pilot"
    assert summary["pilot_eligible"] is True


def test_full_real_run_can_be_headline_only_when_all_conditions_hold(monkeypatch) -> None:
    monkeypatch.setattr(runner, "get_settings", _settings)
    summary = runner._build_summary(
        run_id="full",
        systems=["final_gated"],
        eval_split=EvalSplit.external,
        cases=[object()] * 50,
        results=[_result()],
        trace_rows=[{"trace_id": "t"}],
        audit_rows=[{"case_id": "case-1"}],
        unavailable_systems={},
        full_case_count=50,
        case_selection={"limit": None, "case_id": None, "max_cases": None},
        mock_run=False,
        retrieval_only=False,
        real_run=True,
        reranker_unavailable_any=True,
        run_dir=Path("data/eval_runs/full"),
        usage=LLMUsageTotals(answer_calls=50, total_tokens=1000, usage_reported=True),
    )

    assert summary["headline_scope"] == "full_split"
    assert summary["headline_eligible"] is True
    assert summary["expected_rewrite_used"] is False


def test_vector_unavailable_real_run_cannot_be_headline(monkeypatch) -> None:
    monkeypatch.setattr(runner, "get_settings", _settings)
    summary = runner._build_summary(
        run_id="full-vector-fallback",
        systems=["final_gated"],
        eval_split=EvalSplit.external,
        cases=[object()] * 50,
        results=[_result()],
        trace_rows=[{"trace_id": "t"}],
        audit_rows=[{"case_id": "case-1"}],
        unavailable_systems={},
        full_case_count=50,
        case_selection={"limit": None, "case_id": None, "max_cases": None},
        mock_run=False,
        retrieval_only=False,
        real_run=True,
        reranker_unavailable_any=False,
        vector_unavailable_any=True,
        run_dir=Path("data/eval_runs/full-vector-fallback"),
        usage=LLMUsageTotals(answer_calls=50, total_tokens=1000, usage_reported=True),
    )

    assert summary["headline_eligible"] is False
    assert summary["vector_unavailable"] is True


def test_mock_run_is_smoke_scope() -> None:
    summary = runner._build_summary(
        run_id="mock",
        systems=["final_gated"],
        eval_split=EvalSplit.fixture,
        cases=[object()],
        results=[_result()],
        trace_rows=[{"trace_id": "t"}],
        audit_rows=[{"case_id": "case-1"}],
        unavailable_systems={},
        full_case_count=36,
        case_selection={"limit": None, "case_id": None, "max_cases": None},
        mock_run=True,
        retrieval_only=False,
        real_run=False,
        reranker_unavailable_any=False,
        run_dir=Path("data/eval_runs/mock"),
        usage=LLMUsageTotals(),
    )

    assert summary["headline_scope"] == "smoke"
    assert summary["headline_eligible"] is False
    assert summary["mock_used"] is True
