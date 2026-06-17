from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import app.eval.runner as runner
from app.core.enums import EvalSplit
from app.eval.dataset import read_jsonl
from app.eval.redteam_metrics import compute_redteam_metrics
from app.ingest.loader import load_corpus
from app.ingest.parser_markdown import parse_markdown_document
from app.llm.usage import LLMUsageTotals
from app.schemas.eval import EvalResult
from scripts.ingest_corpus import run_ingest


def test_include_redteam_default_false_keeps_default_index_clean(tmp_path: Path) -> None:
    sample_root = tmp_path / "sample"
    redteam_root = tmp_path / "redteam"
    output_root = tmp_path / "generated"
    _write_fixture_doc(sample_root / "fixture.md", "doc-fixture", "synthetic_fixture")
    _write_fixture_doc(redteam_root / "poison.md", "doc-redteam-test", "redteam_injection")

    summary = run_ingest(
        input_dir=sample_root,
        output_dir=output_root,
        eval_path=None,
        review_path=None,
        redteam_input_dir=redteam_root,
    )

    chunks = read_jsonl(output_root / "chunks.jsonl")
    assert summary["include_redteam"] is False
    assert summary["loaded_redteam_files"] == 0
    assert {chunk["corpus_source"] for chunk in chunks} == {"synthetic_fixture"}
    assert all(not chunk["doc_id"].startswith("doc-redteam") for chunk in chunks)


def test_include_redteam_true_adds_only_explicit_redteam_corpus(tmp_path: Path) -> None:
    sample_root = tmp_path / "sample"
    redteam_root = tmp_path / "redteam"
    output_root = tmp_path / "generated"
    _write_fixture_doc(sample_root / "fixture.md", "doc-fixture", "synthetic_fixture")
    _write_fixture_doc(redteam_root / "poison.md", "doc-redteam-test", "redteam_injection")

    summary = run_ingest(
        input_dir=sample_root,
        output_dir=output_root,
        eval_path=None,
        review_path=None,
        include_redteam=True,
        redteam_input_dir=redteam_root,
    )

    chunks = read_jsonl(output_root / "chunks.jsonl")
    assert summary["loaded_redteam_files"] == 1
    assert {chunk["corpus_source"] for chunk in chunks} == {
        "synthetic_fixture",
        "redteam_injection",
    }


def test_redteam_corpus_documents_are_marked_redteam_injection() -> None:
    raw_docs = load_corpus(Path("data/redteam_corpus"))
    parsed = [parse_markdown_document(raw_doc) for raw_doc in raw_docs]

    assert len(parsed) == 10
    assert {
        parsed_doc.metadata.corpus_source.value for parsed_doc in parsed
    } == {"redteam_injection"}


def test_redteam_metrics_count_synthetic_injection_success() -> None:
    metrics = compute_redteam_metrics(
        [
            {
                "case_id": "RT-001",
                "auto_injection_success": True,
                "clean": {"response_mode": "answer"},
                "poisoned": {
                    "response_mode": "answer",
                    "citations": [
                        {
                            "doc_id": "doc-redteam-rt-001",
                            "chunk_id": "doc-redteam-rt-001::chunk-0000",
                        }
                    ],
                },
            }
        ]
    )

    assert metrics["injection_success_count"] == 1
    assert metrics["injection_success_rate"] == 1.0
    assert metrics["poisoned_citation_count"] == 1
    assert metrics["poisoned_citation_rate"] == 1.0


def test_redteam_metrics_count_unaffected_pair_as_zero() -> None:
    metrics = compute_redteam_metrics(
        [
            {
                "case_id": "RT-010",
                "clean": {"response_mode": "refuse_no_evidence"},
                "poisoned": {"response_mode": "refuse_no_evidence", "citations": []},
                "gate_applicable": True,
            }
        ]
    )

    assert metrics["injection_success_count"] == 0
    assert metrics["injection_success_rate"] == 0.0
    assert metrics["gate_bypass_count"] == 0
    assert metrics["gate_bypass_rate"] == 0.0


def test_redteam_summary_is_never_headline_eligible(monkeypatch) -> None:
    monkeypatch.setattr(runner, "get_settings", _settings)
    summary = runner._build_summary(
        run_id="redteam",
        systems=["final_gated_calibrated"],
        eval_split=EvalSplit.redteam,
        cases=[object()] * 10,
        results=[_result()],
        trace_rows=[{"trace_id": "t"}],
        audit_rows=[{"case_id": "RT-001"}],
        unavailable_systems={},
        full_case_count=10,
        case_selection={"limit": None, "case_id": None, "max_cases": None},
        mock_run=False,
        retrieval_only=False,
        real_run=True,
        reranker_unavailable_any=True,
        run_dir=Path("data/eval_runs/redteam"),
        usage=LLMUsageTotals(answer_calls=20, total_tokens=1000, usage_reported=True),
    )

    assert summary["headline_eligible"] is False
    assert summary["headline_scope"] == "redteam"
    assert summary["redteam_run"] is True
    assert summary["redteam_headline_policy"]


def _write_fixture_doc(path: Path, doc_id: str, corpus_source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"doc_id: {doc_id}",
                "title: Test Document",
                "doc_type: faq",
                "status: active",
                "version: v1",
                "access_level: internal",
                "allowed_roles:",
                "  - employee",
                f"source_path: {path.as_posix()}",
                f"corpus_source: {corpus_source}",
                "source_origin: generated",
                "metadata_origin: native",
                "---",
                "",
                "# Test Document",
                "",
                "## Body",
                "",
                "This document has one searchable fixture paragraph.",
            ]
        ),
        encoding="utf-8",
    )


def _result() -> EvalResult:
    return EvalResult(
        case_id="RT-001",
        system_name="final_gated_calibrated",
        eval_split=EvalSplit.redteam,
        corpus_source="redteam_injection",
        raw_correct=True,
        grounded_correct=True,
        citation_valid=True,
        refused=False,
        metrics={"grounded_correct": True, "citation_valid": True},
    )


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider="deepseek",
        llm_model_name="deepseek-v4-flash",
        rewrite_llm_provider="rule_based",
        rewrite_llm_model_name="deepseek-v4-flash",
        reranker_provider="bge",
    )
