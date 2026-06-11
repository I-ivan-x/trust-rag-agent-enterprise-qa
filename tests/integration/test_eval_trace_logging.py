import json
from pathlib import Path

from app.eval.runner import run_eval


def test_eval_trace_logging_contains_retrieval_fields(tmp_path: Path) -> None:
    run_eval(
        split="fixture",
        systems=["final_gated"],
        mock_run=True,
        output_root=tmp_path,
        run_id="test-trace",
        write_reports=False,
    )
    trace_path = tmp_path / "test-trace" / "traces.jsonl"
    first_trace = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])

    assert first_trace["trace_id"]
    assert first_trace["retrieved_chunk_ids"]
    assert first_trace["events"][0]["step"] == "load_case"
    assert first_trace["expected_rewrite_policy"] == "informational_only"
