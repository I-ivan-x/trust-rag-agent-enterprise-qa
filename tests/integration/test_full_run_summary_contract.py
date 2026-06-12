from __future__ import annotations

import json
from pathlib import Path

from app.eval.runner import run_eval


def test_full_split_summary_contract_for_mock_run(tmp_path: Path) -> None:
    summary = run_eval(
        split="fixture",
        systems=["final_gated"],
        mock_run=True,
        output_root=tmp_path,
        run_id="contract",
        write_reports=False,
    )
    summary_path = tmp_path / "contract" / "summary.json"
    loaded = json.loads(summary_path.read_text(encoding="utf-8"))
    traces = (tmp_path / "contract" / "traces.jsonl").read_text(encoding="utf-8")
    reports = json.dumps(loaded, ensure_ascii=False)

    assert loaded == summary
    assert loaded["num_cases"] == 36
    assert loaded["full_case_count"] == 36
    assert loaded["expected_rewrite_used"] is False
    assert loaded["llm_call_count"] == 0
    assert "DEEPSEEK_API_KEY" not in reports
    assert "sk-" not in reports
    assert "sk-" not in traces

