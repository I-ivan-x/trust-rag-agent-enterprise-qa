from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import app.eval.runner as runner
from app.answer.citation_binder import BoundClaim
from app.core.enums import DecisionReason, ExpectedBehavior
from app.eval.real_pipeline import RealFinalResult
from app.schemas.citation import Citation, CitationLocator
from app.schemas.eval import EvalCase, EvalResult
from tests.helpers import make_retrieved_chunk


def _case(expected_behavior: str = "answer") -> EvalCase:
    return EvalCase(
        case_id="external-001",
        split="external",
        query="How do I configure CORS?",
        query_type="fact_lookup",
        corpus_source="public_external",
        expected_behavior=expected_behavior,
        gold_doc_ids=["doc-cors"],
        gold_chunk_ids=["chunk-cors"],
        reference_claims=["Use CORSMiddleware."],
    )


def _citation(chunk_id: str = "chunk-cors") -> Citation:
    return Citation(
        citation_id="CIT-0001",
        doc_id="doc-cors",
        chunk_id=chunk_id,
        title="CORS",
        section_path=["CORS", "Use CORSMiddleware"],
        locator=CitationLocator(source_path="doc-cors#L10-L12", line_start=10, line_end=12),
    )


def _real_result(
    *,
    refused: bool = False,
    claims: list[BoundClaim] | None = None,
    citations: list[Citation] | None = None,
) -> RealFinalResult:
    return RealFinalResult(
        reranked_chunks=[
            make_retrieved_chunk(
                "chunk-cors",
                "Use CORSMiddleware to configure CORS.",
                doc_id="doc-cors",
            )
        ],
        first_pass_reranked=None,
        refused=refused,
        decision_reason=(
            DecisionReason.no_evidence if refused else DecisionReason.none
        ),
        response_mode=(
            ExpectedBehavior.refuse_no_evidence if refused else ExpectedBehavior.answer
        ),
        citations=citations or [],
        answer_text=(
            "I do not have enough provided evidence to answer this question."
            if refused
            else "Use CORSMiddleware."
        ),
        rewrite_source="none",
        actual_rewritten_query=None,
        rewrite_model_name=None,
        rewrite_reason=None,
        second_pass_attempted=False,
        reranker_unavailable=False,
        claims=claims or [],
        warnings=[],
        used_real_llm_answer=not refused,
    )


def test_answer_row_freezes_claim_citations_and_chunk_text_sha() -> None:
    claim = BoundClaim(
        claim_id="claim-0001",
        text="Use CORSMiddleware.",
        supporting_chunk_ids=["chunk-cors"],
        citation_ids=["CIT-0001"],
    )
    real = _real_result(claims=[claim], citations=[_citation()])

    row = runner._answer_row(
        run_id="audit-run",
        case=_case(),
        system_name="final_agentic",
        real=real,
    )

    assert row["run_id"] == "audit-run"
    assert row["case_id"] == "external-001"
    assert row["system_name"] == "final_agentic"
    assert row["refused"] is False
    assert row["claims"][0]["supporting_chunk_ids"] == ["chunk-cors"]
    assert row["citations"][0]["chunk_id"] == "chunk-cors"
    text = row["cited_chunk_texts"]["chunk-cors"]
    assert text == "Use CORSMiddleware to configure CORS."
    assert row["cited_text_sha256"]["chunk-cors"] == sha256(
        text.encode("utf-8")
    ).hexdigest()
    assert row["warnings"] == []


def test_answer_row_warns_when_cited_chunk_is_missing_from_reranked() -> None:
    row = runner._answer_row(
        run_id="audit-run",
        case=_case(),
        system_name="final_agentic",
        real=_real_result(citations=[_citation("missing-chunk")]),
    )

    assert row["cited_chunk_texts"]["missing-chunk"] is None
    assert row["cited_text_sha256"]["missing-chunk"] is None
    assert "cited_chunk_not_in_reranked:missing-chunk" in row["warnings"]


def test_answer_row_for_refusal_has_empty_claims_and_citations() -> None:
    row = runner._answer_row(
        run_id="audit-run",
        case=_case("refuse_no_evidence"),
        system_name="final_agentic",
        real=_real_result(refused=True),
    )

    assert row["refused"] is True
    assert row["response_mode"] == "refuse_no_evidence"
    assert row["claims"] == []
    assert row["citations"] == []
    assert row["cited_chunk_texts"] == {}
    assert row["cited_text_sha256"] == {}


def test_run_eval_writes_answers_jsonl(monkeypatch, tmp_path: Path) -> None:
    case = _case()
    answer = {"run_id": "audit-run", "case_id": case.case_id, "claims": []}
    result = EvalResult(
        case_id=case.case_id,
        system_name="final_agentic",
        eval_split="external",
        corpus_source="public_external",
        raw_correct=True,
        grounded_correct=True,
        citation_valid=True,
        refused=False,
        decision_reason="none",
        metrics={"grounded_correct": True},
    )

    monkeypatch.setattr(runner, "load_eval_cases", lambda split: [case])
    monkeypatch.setattr(runner, "load_chunks_for_split", lambda split: [])
    monkeypatch.setattr(
        runner,
        "_run_case",
        lambda *args, **kwargs: {
            "result": result,
            "trace": {"trace_id": "trace-1"},
            "audit": None,
            "answer": answer,
            "failure": {},
        },
    )

    runner.run_eval(
        split="external",
        systems=["final_agentic"],
        mock_run=True,
        output_root=tmp_path,
        run_id="audit-run",
        write_reports=False,
    )

    rows = [
        json.loads(line)
        for line in (tmp_path / "audit-run" / "answers.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert rows == [answer]
