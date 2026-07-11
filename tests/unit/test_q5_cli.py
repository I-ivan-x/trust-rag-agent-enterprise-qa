from __future__ import annotations

import pytest

from app.eval.q5_runner import Q5RunSettings
from scripts.grade_q5_run import build_parser as build_grade_parser
from scripts.run_q5_tasks import build_parser as build_run_parser


def test_q5_runtime_cli_has_no_gold_surface_and_exposes_execution_inputs() -> None:
    parser = build_run_parser()
    destinations = {action.dest for action in parser._actions}

    assert "gold" not in destinations
    assert {"tasks", "environment", "runtime_cases", "mode", "model_role"} <= (
        destinations
    )


def test_q5_grader_cli_separates_grade_and_dual_summary_commands() -> None:
    parser = build_grade_parser()
    grade = parser.parse_args(
        ["grade", "--run-dir", "run", "--gold", "gold.jsonl"]
    )
    summarize = parser.parse_args(
        [
            "summarize",
            "--primary-run",
            "primary",
            "--confirmatory-run",
            "confirmatory",
            "--output-dir",
            "combined",
        ]
    )

    assert grade.command == "grade"
    assert summarize.command == "summarize"


def test_q5_run_settings_reject_self_reported_provider_and_run_counts(tmp_path) -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        Q5RunSettings(
            output_root=tmp_path,
            run_id="self-report-rejected",
            provider="claimed-real",
            mock_used=False,
            real_run=True,
            test_run_count_by_model_role={"primary": 1, "confirmatory": 1},
        )
