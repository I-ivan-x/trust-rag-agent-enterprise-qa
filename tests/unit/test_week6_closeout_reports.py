from __future__ import annotations

import json
from pathlib import Path

REPORT_PATHS = [
    Path("docs/EVALUATION_REPORT.md"),
    Path("docs/FAILURE_ANALYSIS.md"),
    Path("docs/CITATION_AUDIT.md"),
    Path("docs/WEEK6_CLOSEOUT_REVIEW_PACKET.md"),
]


def test_week6_closeout_reports_keep_metric_boundaries() -> None:
    evaluation = Path("docs/EVALUATION_REPORT.md").read_text(encoding="utf-8")
    failure = Path("docs/FAILURE_ANALYSIS.md").read_text(encoding="utf-8")
    citation = Path("docs/CITATION_AUDIT.md").read_text(encoding="utf-8")
    packet = Path("docs/WEEK6_CLOSEOUT_REVIEW_PACKET.md").read_text(encoding="utf-8")
    normalized_evaluation = " ".join(evaluation.split())

    assert (
        "Retrieval-tier metrics measure whether gold evidence is retrieved, "
        "not whether the final answer is correct."
    ) in normalized_evaluation
    assert "final_agentic did not outperform final_gated" in evaluation
    assert "hard_negative_error_rate=1.0 indicates a serious failure mode." in failure
    assert "Current citation audit is rule-based v1" in citation
    assert "Safe-to-Cite Claims" in packet
    assert "Unsafe-to-Cite Claims" in packet


def test_week6_reports_and_artifacts_do_not_leak_api_keys() -> None:
    rendered = "".join(path.read_text(encoding="utf-8") for path in REPORT_PATHS)
    for summary_path in Path("data/eval_runs").glob("*/summary.json"):
        rendered += json.dumps(json.loads(summary_path.read_text(encoding="utf-8")))
    for trace_path in Path("data/eval_runs").glob("*/traces.jsonl"):
        rendered += trace_path.read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY" not in rendered
    assert "OPENAI_API_KEY" not in rendered
    assert "sk-" not in rendered
