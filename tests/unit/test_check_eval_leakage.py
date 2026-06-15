import json
from pathlib import Path

import scripts.check_eval_leakage as leakage_script
from app.schemas.chunk import Chunk


def _chunk(
    *,
    chunk_id: str,
    doc_id: str,
    text: str,
    section_path: list[str],
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        chunk_index=0,
        text=text,
        section_path=section_path,
        token_count=10,
        char_count=len(text),
        version="test",
    )


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


def test_check_eval_leakage_flags_no_retrievable_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(leakage_script, "LEAKAGE_REPORT_JSON", tmp_path / "report.json")
    monkeypatch.setattr(leakage_script, "LEAKAGE_REPORT_MD", tmp_path / "report.md")
    monkeypatch.setattr(
        leakage_script,
        "load_chunks_for_split",
        lambda split: [
            _chunk(
                chunk_id="gold::chunk-0000",
                doc_id="gold",
                text="The access token lifetime is 30 minutes.",
                section_path=["Access Token Lifetime"],
            )
        ],
    )
    path = tmp_path / "fixture_eval.jsonl"
    record = {
        "case_id": "case-1",
        "split": "fixture",
        "query": "Use the relevant side A guidance.",
        "query_type": "single_doc_fact",
        "expected_behavior": "answer",
        "gold_doc_ids": ["gold"],
        "gold_chunk_ids": ["gold::chunk-0000"],
        "requires_citation": True,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    report = leakage_script.check_leakage(input_path=path)

    assert report["passed"] is False
    assert [flag["flag_type"] for flag in report["blocking_flags"]] == ["no_retrievable_content"]


def test_hard_negative_high_title_overlap_is_non_blocking(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(leakage_script, "LEAKAGE_REPORT_JSON", tmp_path / "report.json")
    monkeypatch.setattr(leakage_script, "LEAKAGE_REPORT_MD", tmp_path / "report.md")
    monkeypatch.setattr(
        leakage_script,
        "load_chunks_for_split",
        lambda split: [
            _chunk(
                chunk_id="hard-gold::chunk-0000",
                doc_id="hard-gold",
                text=(
                    "Path parameters can enforce numeric validations such as greater than or equal."
                ),
                section_path=["Path Parameters and Numeric Validations"],
            )
        ],
    )
    path = tmp_path / "hard_negative_eval.jsonl"
    record = {
        "case_id": "hard-negative-017",
        "split": "hard_negative",
        "query": "Path parameters with numeric validations",
        "query_type": "hard_negative",
        "corpus_source": "hard_negative",
        "expected_behavior": "answer",
        "gold_doc_ids": ["hard-gold"],
        "gold_chunk_ids": ["hard-gold::chunk-0000"],
        "requires_citation": True,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    report = leakage_script.check_leakage(input_path=path)

    assert report["passed"] is True
    assert report["flags"][0]["flag_type"] == "high_title_overlap"
    assert report["flags"][0]["blocking"] is False
