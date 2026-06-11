from pathlib import Path

from app.eval.runner import run_eval


def test_run_eval_fixture_mock_writes_artifacts(tmp_path: Path) -> None:
    summary = run_eval(
        split="fixture",
        systems=["final_gated"],
        mock_run=True,
        output_root=tmp_path,
        run_id="test-fixture-mock",
        write_reports=False,
    )
    run_dir = tmp_path / "test-fixture-mock"

    assert summary["num_cases"] == 36
    assert summary["headline_eligible"] is False
    assert (run_dir / "results.jsonl").exists()
    assert (run_dir / "traces.jsonl").exists()
    assert (run_dir / "summary.json").exists()
