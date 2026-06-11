import json
from pathlib import Path

import scripts.check_eval_leakage as leakage_script


def test_check_eval_leakage_updates_title_overlap_for_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(leakage_script, "LEAKAGE_REPORT_JSON", tmp_path / "report.json")
    monkeypatch.setattr(leakage_script, "LEAKAGE_REPORT_MD", tmp_path / "report.md")
    path = tmp_path / "fixture_eval.jsonl"
    record = {
        "case_id": "case-1",
        "split": "fixture",
        "query": "What is the token lifetime?",
        "query_type": "single_doc_fact",
        "expected_behavior": "answer",
        "gold_doc_ids": ["doc-api-auth-service-v2"],
        "gold_chunk_ids": ["doc-api-auth-service-v2::chunk-0000"],
        "reference_claims": ["The token lifetime is 30 minutes."],
        "requires_citation": True,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    report = leakage_script.check_leakage(input_path=path)
    updated = path.read_text(encoding="utf-8")

    assert report["case_count"] == 1
    assert "title_overlap_score" in updated
