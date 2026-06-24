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


def test_check_eval_leakage_can_use_corpus_overlay(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    _write_seeded_doc(corpus / "active" / "sop-alpha.md")
    overlay_path = corpus / "overlay" / "metadata_overlay.yaml"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.write_text(
        """seed: 1
defaults:
  status: active
  access_level: internal
documents: []
""",
        encoding="utf-8",
    )
    eval_path = tmp_path / "ops_runbook_action_v1_eval.jsonl"
    eval_path.write_text(
        json.dumps(
            {
                "case_id": "ora-test",
                "split": "fixture",
                "query": "Which remediation token is supported?",
                "query_type": "fact_lookup",
                "expected_behavior": "answer",
                "gold_doc_ids": ["sop-alpha"],
                "requires_citation": True,
                "gold_condition": "CONFIG_VIOLATION",
                "gold_action": "open_remediation_ticket",
                "authorized": True,
                "expected_tier": "approval",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = leakage_script.check_leakage(
        input_path=eval_path,
        corpus_dir=corpus,
        overlay_path=overlay_path,
        update_cases=False,
        report_json_path=tmp_path / "report.json",
        report_md_path=tmp_path / "report.md",
    )

    assert report["passed"] is True
    assert report["flags"] == []


def test_check_eval_leakage_flags_missing_gold_doc_with_corpus(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    _write_seeded_doc(corpus / "active" / "sop-alpha.md")
    eval_path = tmp_path / "ops_runbook_action_v1_eval.jsonl"
    eval_path.write_text(
        json.dumps(
            {
                "case_id": "ora-test",
                "split": "fixture",
                "query": "Which remediation token is supported?",
                "query_type": "fact_lookup",
                "expected_behavior": "answer",
                "gold_doc_ids": ["missing-doc"],
                "requires_citation": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = leakage_script.check_leakage(
        input_path=eval_path,
        corpus_dir=corpus,
        update_cases=False,
        report_json_path=tmp_path / "report.json",
        report_md_path=tmp_path / "report.md",
    )

    assert report["passed"] is False
    assert "missing_gold_doc" in [flag["flag_type"] for flag in report["blocking_flags"]]


def _write_seeded_doc(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
doc_id: sop-alpha
title: Alpha Evidence
doc_type: public_doc
status: active
version: q3-test
access_level: internal
allowed_roles: [admin, editor]
language: en
source_path: {path.as_posix()}
corpus_source: public_external
source_origin: generated
source_license_note: Seeded overlay fixture.
metadata_origin: seeded_overlay
---

# Alpha Evidence

This seeded document supports the remediation token used by the eval case.
""",
        encoding="utf-8",
    )
