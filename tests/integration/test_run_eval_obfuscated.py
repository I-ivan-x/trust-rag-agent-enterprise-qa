import json
from pathlib import Path

from app.eval.runner import run_eval


def test_run_eval_obfuscated_does_not_flow_expected_rewrite(tmp_path: Path) -> None:
    summary = run_eval(
        split="obfuscated",
        systems=["final_gated", "final_agentic"],
        mock_run=True,
        output_root=tmp_path,
        run_id="test-obfuscated",
        write_reports=False,
    )
    traces = [
        json.loads(line)
        for line in (tmp_path / "test-obfuscated" / "traces.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    agentic_traces = [trace for trace in traces if trace["system_name"] == "final_agentic"]

    assert summary["headline_eligible"] is False
    assert summary["toy_retrieval"] is True
    assert agentic_traces
    assert all("Need the FastAPI bit for case" not in trace["query"] for trace in traces)
    for trace in agentic_traces:
        if trace["retrieval_query"] == trace["expected_rewrite"]:
            assert trace["rewrite_source"] == "rule_based_query_rewriter"
            assert trace["actual_rewritten_query"] == trace["expected_rewrite"]
        else:
            assert trace["expected_rewrite_policy"] == "informational_only"

