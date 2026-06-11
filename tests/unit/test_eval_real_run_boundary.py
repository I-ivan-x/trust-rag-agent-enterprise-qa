from types import SimpleNamespace

import pytest

from app.eval import runner
from app.eval.runner import run_eval


def test_mock_run_is_not_headline(tmp_path) -> None:
    summary = run_eval(
        split="fixture",
        systems=["final_gated"],
        mock_run=True,
        output_root=tmp_path,
        run_id="mock-boundary",
        write_reports=False,
    )

    assert summary["headline_eligible"] is False
    assert summary["uses_real_llm"] is False
    assert summary["mock_run_note"]


def test_real_run_with_mock_llm_fails_before_simulation(monkeypatch, tmp_path) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("_simulate_final_response must not run during real-run")

    monkeypatch.setattr(runner, "_simulate_final_response", fail_if_called)
    monkeypatch.setattr(
        runner,
        "get_settings",
        lambda: SimpleNamespace(llm_provider="mock", openai_api_key=None, eval_runs_dir=tmp_path),
    )

    with pytest.raises(RuntimeError, match="Current LLM_PROVIDER=mock"):
        run_eval(
            split="external",
            systems=["final_gated"],
            real_run=True,
            output_root=tmp_path,
            run_id="real-boundary",
            write_reports=False,
        )

