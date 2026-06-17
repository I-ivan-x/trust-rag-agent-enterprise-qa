from __future__ import annotations

import json
from pathlib import Path

import app.eval.runner as runner
import scripts.check_eval_regression as regression
from app.core.enums import EvalSplit
from app.llm.usage import LLMUsageTotals
from app.schemas.eval import EvalResult


def test_regression_checker_passes_matching_summary(tmp_path: Path, capsys) -> None:
    baseline_path = _write_baseline(tmp_path)
    summary_path = _write_summary(tmp_path, grounded_correctness=0.24)

    exit_code = regression.main(["--baseline", str(baseline_path), str(summary_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PASS" in captured.out
    assert "Regression gate passed" in captured.out


def test_regression_checker_fails_regressed_summary(tmp_path: Path, capsys) -> None:
    baseline_path = _write_baseline(tmp_path)
    summary_path = _write_summary(tmp_path, grounded_correctness=0.10)

    exit_code = regression.main(["--baseline", str(baseline_path), str(summary_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "REGRESSION" in captured.out
    assert "Regression gate failed" in captured.out


def test_mock_summary_cannot_be_headline_eligible() -> None:
    summary = runner._build_summary(
        run_id="mock-regression-invariant",
        systems=["final_gated"],
        eval_split=EvalSplit.fixture,
        cases=[object()],
        results=[
            EvalResult(
                case_id="fixture-001",
                system_name="final_gated",
                eval_split=EvalSplit.fixture,
                corpus_source="synthetic_fixture",
                raw_correct=True,
                grounded_correct=True,
                citation_valid=True,
                refused=False,
                metrics={"grounded_correct": True, "citation_valid": True},
            )
        ],
        trace_rows=[{"trace_id": "trace-1"}],
        audit_rows=[{"case_id": "fixture-001"}],
        unavailable_systems={},
        full_case_count=36,
        case_selection={"limit": None, "case_id": None, "max_cases": None},
        mock_run=True,
        retrieval_only=False,
        real_run=False,
        reranker_unavailable_any=False,
        run_dir=Path("data/eval_runs/mock-regression-invariant"),
        usage=LLMUsageTotals(),
    )

    assert summary["mock_used"] is True
    assert summary["headline_eligible"] is False
    assert summary["headline_scope"] == "smoke"


def _write_baseline(tmp_path: Path) -> Path:
    baseline = [
        {
            "metric": "grounded_correctness",
            "split": "external",
            "system": "final_gated",
            "mode": "real_run",
            "baseline_value": 0.24,
            "direction": ">=",
            "tolerance": 0.02,
            "required_num_cases": 50,
            "require_headline_eligible": True,
            "source_run_id": "q2-p1-06-reconciled-legacy-default",
            "note": "Synthetic unit-test slice of the frozen baseline.",
        }
    ]
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    return path


def _write_summary(tmp_path: Path, *, grounded_correctness: float) -> Path:
    summary = {
        "run_id": "synthetic-real-summary",
        "split": "external",
        "eval_split": "external",
        "mode": "real_run",
        "headline_eligible": True,
        "mock_used": False,
        "num_cases": 50,
        "summary_metrics": {
            "final_gated": {
                "grounded_correctness": grounded_correctness,
            }
        },
    }
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    return path
