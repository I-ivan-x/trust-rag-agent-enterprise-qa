from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.diagnosis import diagnose
from app.core.enums import EvalSplit
from app.eval.baselines import retrieve_toy_baseline
from app.eval.dataset import load_chunks_for_split, load_eval_cases, read_jsonl
from app.guards.acl_gate import apply_acl_gate
from app.guards.conflict_detector import ConflictDecision, detect_minimal_conflict
from app.guards.document_state_gate import apply_document_state_gate
from app.guards.evidence_gate import EvidenceGateDecision
from app.ingest.chunker import chunk_documents
from app.ingest.loader import load_corpus
from app.ingest.parser_markdown import parse_markdown_document
from app.schemas.retrieval import RetrievedChunk
from app.workflow.state import RetrievalPassResult
from scripts.ingest_corpus import run_ingest


def test_agent_residual_split_loads_eval_and_chunks() -> None:
    cases = load_eval_cases(EvalSplit.agent_residual)
    chunks = load_chunks_for_split(EvalSplit.agent_residual)

    assert len(cases) == 18
    assert len(chunks) == 33
    assert {case.corpus_source.value for case in cases} == {"agent_residual"}
    assert {chunk.corpus_source.value for chunk in chunks} == {"agent_residual"}


def test_agent_residual_diagnosis_gate_matches_annotations() -> None:
    cases = {case.case_id: case for case in load_eval_cases(EvalSplit.agent_residual)}
    annotations = _annotations()
    chunks = _chunks_from_corpus()
    chunks_by_doc = {chunk.doc_id: chunk for chunk in chunks}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    cooccurrence_count = 0

    for case_id, annotation in annotations.items():
        case = cases[case_id]
        first_pass = _first_pass_for(case_id, case.query, chunks_by_doc)
        report = diagnose(first_pass)
        actual_actions = [action.value for action in report.legal_actions]

        assert report.failure_type.value == annotation["expected_failure_type"]
        assert actual_actions == annotation["expected_legal_actions"]
        if set(actual_actions) == {
            "rewrite_query",
            "filtered_retrieval",
            "refuse_with_explanation",
        }:
            cooccurrence_count += 1

        for chunk_id in case.gold_chunk_ids:
            assert chunk_id in chunks_by_id

        retrieved = retrieve_toy_baseline(
            "final_agentic_v2",
            case.query,
            chunks,
            top_k=10,
        )
        retrieved_gold = {item.chunk.chunk_id for item in retrieved} & set(
            case.gold_chunk_ids
        )
        assert retrieved_gold, f"{case_id} gold chunks were not reachable in top-10"

    assert cooccurrence_count >= 6


def test_agent_residual_annotations_have_required_shape() -> None:
    annotations = list(read_jsonl(Path("data/gold_eval/agent_residual_v1_annotations.jsonl")))
    assert len(annotations) == 18
    assert sum(row["scenario_type"] == "cooccurrence" for row in annotations) >= 6
    assert sum(row["scenario_type"] == "weak_recall_hard" for row in annotations) == 8
    for row in annotations:
        assert set(row) == {
            "case_id",
            "scenario_type",
            "expected_failure_type",
            "expected_legal_actions",
        }


def test_agent_residual_corpus_documents_are_marked_agent_residual() -> None:
    raw_docs = load_corpus(Path("data/agent_residual_corpus"))
    parsed = [parse_markdown_document(raw_doc) for raw_doc in raw_docs]

    assert len(parsed) == 33
    assert {parsed_doc.metadata.corpus_source.value for parsed_doc in parsed} == {
        "agent_residual"
    }


def test_include_agent_residual_default_false_keeps_default_index_clean(
    tmp_path: Path,
) -> None:
    sample_root = tmp_path / "sample"
    residual_root = tmp_path / "agent_residual"
    output_root = tmp_path / "generated"
    _write_fixture_doc(sample_root / "fixture.md", "doc-fixture", "synthetic_fixture")
    _write_fixture_doc(
        residual_root / "residual.md",
        "doc-residual-test",
        "agent_residual",
    )

    summary = run_ingest(
        input_dir=sample_root,
        output_dir=output_root,
        eval_path=None,
        review_path=None,
        agent_residual_input_dir=residual_root,
    )

    chunks = read_jsonl(output_root / "chunks.jsonl")
    assert summary["include_agent_residual"] is False
    assert summary["loaded_agent_residual_files"] == 0
    assert {chunk["corpus_source"] for chunk in chunks} == {"synthetic_fixture"}
    assert all(not chunk["doc_id"].startswith("doc-residual") for chunk in chunks)


def test_include_agent_residual_true_adds_only_explicit_residual_corpus(
    tmp_path: Path,
) -> None:
    sample_root = tmp_path / "sample"
    residual_root = tmp_path / "agent_residual"
    output_root = tmp_path / "generated"
    _write_fixture_doc(sample_root / "fixture.md", "doc-fixture", "synthetic_fixture")
    _write_fixture_doc(
        residual_root / "residual.md",
        "doc-residual-test",
        "agent_residual",
    )

    summary = run_ingest(
        input_dir=sample_root,
        output_dir=output_root,
        eval_path=None,
        review_path=None,
        include_agent_residual=True,
        agent_residual_input_dir=residual_root,
    )

    chunks = read_jsonl(output_root / "chunks.jsonl")
    assert summary["loaded_agent_residual_files"] == 1
    assert {chunk["corpus_source"] for chunk in chunks} == {
        "synthetic_fixture",
        "agent_residual",
    }


def test_agent_residual_summary_is_never_headline_eligible(tmp_path: Path) -> None:
    import app.eval.runner as runner
    from app.llm.usage import LLMUsageTotals
    from app.schemas.eval import EvalResult

    result = EvalResult(
        case_id="AR-001",
        system_name="final_agentic_v2",
        eval_split=EvalSplit.agent_residual,
        corpus_source="agent_residual",
        raw_correct=True,
        grounded_correct=True,
        citation_valid=True,
        refused=False,
        metrics={"grounded_correct": True},
    )

    summary = runner._build_summary(
        run_id="agent-residual",
        systems=["final_agentic_v2"],
        eval_split=EvalSplit.agent_residual,
        cases=[object()] * 10,
        results=[result],
        trace_rows=[{"trace_id": "t"}],
        audit_rows=[{"case_id": "AR-001"}],
        unavailable_systems={},
        full_case_count=10,
        case_selection={"limit": None, "case_id": None, "max_cases": None},
        mock_run=False,
        retrieval_only=False,
        real_run=True,
        reranker_unavailable_any=True,
        run_dir=tmp_path / "agent-residual",
        usage=LLMUsageTotals(answer_calls=10, total_tokens=100, usage_reported=True),
    )

    assert summary["headline_eligible"] is False
    assert summary["headline_scope"] == "agent_residual"
    assert summary["agent_residual_run"] is True
    assert summary["agent_residual_headline_policy"]


def _annotations() -> dict[str, dict[str, Any]]:
    return {
        row["case_id"]: row
        for row in read_jsonl(Path("data/gold_eval/agent_residual_v1_annotations.jsonl"))
    }


def _chunks_from_corpus():
    parsed = [
        parse_markdown_document(raw_doc)
        for raw_doc in load_corpus(Path("data/agent_residual_corpus"))
    ]
    return chunk_documents(parsed)


def _first_pass_for(
    case_id: str,
    query: str,
    chunks_by_doc: dict[str, Any],
) -> RetrievalPassResult:
    if case_id in {f"AR-00{index}" for index in range(1, 7)}:
        selected = [
            chunks_by_doc[f"doc-ar-00{int(case_id[-1])}-gold"],
            chunks_by_doc[f"doc-ar-00{int(case_id[-1])}-old-a"],
            chunks_by_doc[f"doc-ar-00{int(case_id[-1])}-old-b"],
        ]
        return _pass_result(
            query,
            selected,
            evidence_sufficient=False,
            entity_miss=True,
            conflict=False,
        )
    if case_id in {"AR-007", "AR-008"}:
        selected = [chunks_by_doc[f"doc-ar-00{int(case_id[-1])}-gold"]]
        return _pass_result(
            query,
            selected,
            evidence_sufficient=False,
            entity_miss=True,
            conflict=False,
        )
    if case_id == "AR-009":
        return _pass_result(
            query,
            [
                chunks_by_doc["doc-ar-009-gold"],
                chunks_by_doc["doc-ar-009-old-a"],
                chunks_by_doc["doc-ar-009-old-b"],
            ],
            evidence_sufficient=False,
            entity_miss=False,
            conflict=False,
        )
    if case_id == "AR-010":
        return _pass_result(
            query,
            [
                chunks_by_doc["doc-ar-010-conflict-a"],
                chunks_by_doc["doc-ar-010-conflict-b"],
            ],
            evidence_sufficient=False,
            entity_miss=False,
            conflict=True,
        )
    hard_gold_doc_by_case = {
        "AR-H01": "nc-deploy-checklist-2026",
        "AR-H02": "nc-retention-2026",
        "AR-H03": "nc-webhook-retry-2026",
        "AR-H04": "nc-password-policy-2026",
        "AR-H05": "nc-healthcheck",
        "AR-H06": "nc-config-env",
        "AR-H07": "nc-sso-oidc",
        "AR-H08": "nc-pagination-cursor-v2",
    }
    if case_id in hard_gold_doc_by_case:
        return _pass_result(
            query,
            [chunks_by_doc[hard_gold_doc_by_case[case_id]]],
            evidence_sufficient=False,
            entity_miss=True,
            conflict=False,
        )
    raise AssertionError(f"unhandled residual case: {case_id}")


def _pass_result(
    query: str,
    chunks,
    *,
    evidence_sufficient: bool,
    entity_miss: bool,
    conflict: bool,
) -> RetrievalPassResult:
    retrieved = [
        RetrievedChunk(
            chunk=chunk,
            source="hybrid",
            rrf_score=0.9 - (index * 0.01),
            rerank_score=0.9 - (index * 0.01),
            rank=index + 1,
        )
        for index, chunk in enumerate(chunks)
    ]
    state_decision = apply_document_state_gate(retrieved)
    acl_decision = apply_acl_gate(
        state_decision.surviving_chunks,
        user_role="employee",
        user_clearance="internal",
    )
    conflict_decision = (
        detect_minimal_conflict(acl_decision.surviving_chunks)
        if conflict
        else ConflictDecision()
    )
    return RetrievalPassResult(
        query=query,
        retrieved_chunks=retrieved,
        reranked_chunks=retrieved,
        state_decision=state_decision,
        acl_decision=acl_decision,
        conflict_decision=conflict_decision,
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=evidence_sufficient,
            reason="testbed_controlled_signal",
            top_score=0.9,
            support_count=len(acl_decision.surviving_chunks),
            entity_miss=entity_miss,
        ),
    )


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
