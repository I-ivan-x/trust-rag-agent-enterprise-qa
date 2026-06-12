from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.realprovider,
    pytest.mark.skipif(
        not os.environ.get("DEEPSEEK_API_KEY"),
        reason=(
            "real LLM smoke requires DEEPSEEK_API_KEY; skipped by default to avoid "
            "token spend."
        ),
    ),
]


def test_real_run_limit_one_writes_artifacts(tmp_path: Path) -> None:
    from app.eval.runner import run_eval

    summary = run_eval(
        split="fixture",
        systems=["final_gated"],
        real_run=True,
        limit=1,
        max_output_tokens=128,
        output_root=tmp_path,
        run_id="real-smoke",
        write_reports=False,
    )
    run_dir = tmp_path / "real-smoke"

    assert summary["mode"] == "real_run"
    assert summary["uses_real_llm"] is True
    assert summary["expected_rewrite_used"] is False
    assert summary["mock_used"] is False
    assert summary["toy_retrieval"] is False
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "traces.jsonl").exists()
    assert (run_dir / "citation_audit_sample.jsonl").exists()

    traces = [
        json.loads(line)
        for line in (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert traces
    for trace in traces:
        assert trace["retrieval_query"] != trace.get("expected_rewrite")
