from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.enums import DecisionReason, EvalSplit, ExpectedBehavior
from app.eval.baselines import BaselineUnavailable, retrieve_baseline, retrieve_toy_baseline
from app.eval.citation_audit import verify_citations
from app.eval.dataset import load_chunks_for_split, load_eval_cases, write_jsonl
from app.eval.metrics import grounded_correctness, retrieval_metrics, summarize_results
from app.eval.report import (
    write_citation_audit_doc,
    write_eval_report,
    write_failure_analysis,
)
from app.observability.tracing import make_trace_event, now_iso
from app.retrieval.query_rewriter import rewrite_query_for_evidence
from app.schemas.citation import Citation, CitationLocator
from app.schemas.eval import EvalCase, EvalResult, EvalRunSummary
from app.schemas.retrieval import RetrievedChunk

RETRIEVAL_SYSTEMS = {"vector_only", "bm25_only", "hybrid_rrf", "hybrid_rrf_rerank"}
FINAL_SYSTEMS = {"final_gated", "final_agentic"}


def run_eval(
    *,
    split: EvalSplit | str,
    systems: list[str],
    mock_run: bool = False,
    retrieval_only: bool = False,
    real_run: bool = False,
    output_root: Path | None = None,
    run_id: str | None = None,
    write_reports: bool = True,
) -> dict[str, Any]:
    eval_split = EvalSplit(split)
    _validate_mode(systems, mock_run=mock_run, retrieval_only=retrieval_only, real_run=real_run)
    if real_run:
        _require_real_run_ready()

    selected_run_id = run_id or _make_run_id(eval_split)
    run_dir = (output_root or get_settings().eval_runs_dir) / selected_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    cases = load_eval_cases(eval_split)
    chunks = load_chunks_for_split(eval_split)
    results: list[EvalResult] = []
    result_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    unavailable_systems: dict[str, str] = {}

    for system_name in systems:
        for case in cases:
            try:
                row = _run_case(
                    case,
                    system_name,
                    chunks,
                    retrieval_only=retrieval_only,
                    mock_run=mock_run,
                )
            except BaselineUnavailable as exc:
                if exc.fatal:
                    raise
                unavailable_systems[system_name] = str(exc)
                break
            result = row["result"]
            results.append(result)
            result_rows.append(result.model_dump(mode="json"))
            trace_rows.append(row["trace"])
            if row["audit"] is not None:
                audit_rows.append(row["audit"])
            if _is_failure(result, case):
                failure_rows.append(row["failure"])

    summary = EvalRunSummary(
        run_id=selected_run_id,
        systems=systems,
        eval_split=eval_split,
        num_cases=len(cases),
        summary_metrics=summarize_results(results),
        uses_real_embedding=_uses_real_embedding(systems, retrieval_only, unavailable_systems),
        uses_real_reranker=_uses_real_reranker(systems, retrieval_only, unavailable_systems),
        uses_real_llm=False,
    ).model_dump(mode="json")
    summary.update(
        {
            "split": eval_split.value,
            "mode": _mode_name(mock_run=mock_run, retrieval_only=retrieval_only, real_run=real_run),
            "headline_eligible": False,
            "formal_retrieval_baseline": bool(retrieval_only),
            "toy_retrieval": bool(mock_run),
            "unavailable_systems": unavailable_systems,
            "expected_rewrite_policy": (
                "expected_rewrite is informational only and is never used for "
                "retrieval or scoring."
            ),
            "invalidated_previous_runs_note": (
                "Previous obfuscated/agentic smoke results generated before the "
                "expected_rewrite isolation fix are invalidated and must not be cited."
            ),
            "mock_run_note": (
                "Mock/simulated eval runs use toy retrieval smoke only and must not "
                "be used as headline metrics."
                if mock_run
                else None
            ),
            "run_dir": run_dir.as_posix(),
        }
    )

    write_jsonl(run_dir / "results.jsonl", result_rows)
    write_jsonl(run_dir / "traces.jsonl", trace_rows)
    write_jsonl(run_dir / "failures.jsonl", failure_rows)
    write_jsonl(run_dir / "citation_audit_sample.jsonl", audit_rows[:25])
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if write_reports:
        write_eval_report(Path("docs/EVALUATION_REPORT.md"), summary)
        write_failure_analysis(Path("docs/FAILURE_ANALYSIS.md"), failure_rows)
        write_citation_audit_doc(Path("docs/CITATION_AUDIT.md"), audit_rows[:25])
    return summary


def _run_case(
    case: EvalCase,
    system_name: str,
    chunks: list[Any],
    *,
    retrieval_only: bool,
    mock_run: bool,
) -> dict[str, Any]:
    trace_id = f"trace-{case.case_id}-{system_name}"
    retrieval_query = case.query
    first_pass_metrics: dict[str, Any] | None = None
    rewrite_decision = (
        rewrite_query_for_evidence(case.query)
        if system_name == "final_agentic"
        else None
    )
    actual_rewritten_query = (
        rewrite_decision.rewritten_query
        if rewrite_decision and rewrite_decision.should_rewrite
        else None
    )
    rewrite_source = "rule_based_query_rewriter" if actual_rewritten_query else "none"
    if system_name == "final_agentic" and actual_rewritten_query:
        first_pass = _retrieve(system_name, case.query, chunks, retrieval_only=retrieval_only)
        first_pass_metrics = retrieval_metrics(case, first_pass, k=5)
        retrieval_query = actual_rewritten_query
    trace_events = [
        make_trace_event("load_case", case_id=case.case_id, system_name=system_name),
        make_trace_event(
            "rewrite",
            expected_rewrite=case.expected_rewrite,
            expected_rewrite_policy="informational_only",
            actual_rewritten_query=actual_rewritten_query,
            rewrite_source=rewrite_source,
            rewrite_reason=rewrite_decision.reason if rewrite_decision else "not_agentic",
        ),
        make_trace_event("retrieve", system_name=system_name, query=retrieval_query),
    ]
    retrieved = _retrieve(system_name, retrieval_query, chunks, retrieval_only=retrieval_only)
    metrics = retrieval_metrics(case, retrieved, k=5)
    if first_pass_metrics is not None:
        metrics["first_pass_doc_hit@5"] = first_pass_metrics["doc_hit@5"]
        metrics["second_pass_improvement"] = bool(
            metrics["doc_hit@5"] and not first_pass_metrics["doc_hit@5"]
        )

    audit_payload: dict[str, Any] | None = None
    raw_correct: bool | None = None
    grounded: bool | None = None
    citation_valid: bool | None = None
    refused = False
    decision_reason = DecisionReason.none

    if retrieval_only:
        trace_events.append(make_trace_event("score_retrieval", metrics=metrics))
    else:
        if not mock_run:
            raise RuntimeError("_simulate_final_response is only allowed for --mock-run smoke.")
        response = _simulate_final_response(case, retrieved, mock_run=mock_run)
        refused = response["refused"]
        decision_reason = response["decision_reason"]
        raw_correct = response["raw_correct"]
        audit = verify_citations(
            claims=case.reference_claims,
            citations=response["citations"],
            retrieved_chunks=retrieved,
        )
        citation_valid = audit.citation_valid if case.requires_citation else True
        grounded = grounded_correctness(
            raw_correct=raw_correct,
            citation_valid=citation_valid,
            supports_core_claim=audit.supports_core_claim or not case.requires_citation,
        )
        metrics.update(
            {
                "citation_valid": citation_valid,
                "supports_core_claim": audit.supports_core_claim,
                "grounded_correct": grounded,
            }
        )
        audit_payload = {
            "case_id": case.case_id,
            "system_name": system_name,
            **audit.model_dump(mode="json"),
        }
        trace_events.append(
            make_trace_event(
                "mock_answer" if mock_run else "answer",
                refused=refused,
                decision_reason=decision_reason.value,
            )
        )

    result = EvalResult(
        case_id=case.case_id,
        system_name=system_name,
        eval_split=case.eval_split,
        corpus_source=case.corpus_source,
        raw_correct=raw_correct,
        grounded_correct=grounded,
        citation_valid=citation_valid,
        refused=refused,
        decision_reason=decision_reason,
        rewrite_triggered=actual_rewritten_query is not None,
        trace_id=trace_id,
        metrics=metrics,
    )
    trace = {
        "trace_id": trace_id,
        "run_at": now_iso(),
        "case_id": case.case_id,
        "split": case.eval_split.value,
        "system_name": system_name,
        "query": case.query,
        "retrieval_query": retrieval_query,
        "expected_rewrite": case.expected_rewrite,
        "expected_rewrite_policy": "informational_only",
        "actual_rewritten_query": actual_rewritten_query,
        "rewrite_source": rewrite_source,
        "retrieved_chunk_ids": [item.chunk.chunk_id for item in retrieved[:10]],
        "retrieved_doc_ids": [item.chunk.doc_id for item in retrieved[:10]],
        "events": trace_events,
    }
    return {
        "result": result,
        "trace": trace,
        "audit": audit_payload,
        "failure": {
            "case_id": case.case_id,
            "system_name": system_name,
            "query": case.query,
            "reason": _failure_reason(result, case),
            "metrics": metrics,
        },
    }


def _retrieve(
    system_name: str,
    query: str,
    chunks: list[Any],
    *,
    retrieval_only: bool,
) -> list[RetrievedChunk]:
    if retrieval_only:
        return retrieve_baseline(system_name, query, chunks, top_k=10)
    return retrieve_toy_baseline(system_name, query, chunks, top_k=10)


def _simulate_final_response(
    case: EvalCase,
    retrieved: list[RetrievedChunk],
    *,
    mock_run: bool,
) -> dict[str, Any]:
    del mock_run
    expected = case.expected_behavior
    if expected is ExpectedBehavior.refuse_no_evidence:
        return _refusal(DecisionReason.no_evidence, raw_correct=not retrieved)
    if expected is ExpectedBehavior.refuse_permission:
        return _refusal(DecisionReason.permission_denied, raw_correct=True)

    gold_ids = set(case.gold_chunk_ids)
    cited_chunks = [item for item in retrieved if item.chunk.chunk_id in gold_ids]
    if not cited_chunks and case.gold_doc_ids:
        gold_docs = set(case.gold_doc_ids)
        cited_chunks = [item for item in retrieved if item.chunk.doc_id in gold_docs][:1]
    citations = [_citation_for(item, index) for index, item in enumerate(cited_chunks[:2], 1)]
    raw_correct = bool(cited_chunks) if case.gold_doc_ids else expected is ExpectedBehavior.answer
    decision_reason = DecisionReason.none
    if expected is ExpectedBehavior.warn_deprecated:
        decision_reason = DecisionReason.deprecated_only
    elif expected is ExpectedBehavior.report_conflict:
        decision_reason = DecisionReason.conflict_detected
    return {
        "refused": False,
        "decision_reason": decision_reason,
        "raw_correct": raw_correct,
        "citations": citations,
    }


def _refusal(reason: DecisionReason, *, raw_correct: bool) -> dict[str, Any]:
    return {
        "refused": True,
        "decision_reason": reason,
        "raw_correct": raw_correct,
        "citations": [],
    }


def _citation_for(item: RetrievedChunk, index: int) -> Citation:
    chunk = item.chunk
    return Citation(
        citation_id=f"CIT-{index:04d}",
        doc_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        title=chunk.section_path[0] if chunk.section_path else chunk.doc_id,
        section_path=chunk.section_path,
        locator=CitationLocator(
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            source_path=chunk.doc_id,
        ),
    )


def _validate_mode(
    systems: list[str],
    *,
    mock_run: bool,
    retrieval_only: bool,
    real_run: bool,
) -> None:
    unknown = set(systems) - RETRIEVAL_SYSTEMS - FINAL_SYSTEMS
    if unknown:
        raise ValueError(f"Unsupported systems: {', '.join(sorted(unknown))}")
    selected_modes = sum([mock_run, retrieval_only, real_run])
    if selected_modes != 1:
        raise ValueError("Select exactly one mode: --mock-run, --retrieval-only, or --real-run")
    if retrieval_only and any(system in FINAL_SYSTEMS for system in systems):
        raise ValueError("final_* systems require --mock-run or --real-run")
    if not retrieval_only and any(system in RETRIEVAL_SYSTEMS for system in systems):
        raise ValueError("retrieval baseline systems require --retrieval-only")


def _require_real_run_ready() -> None:
    settings = get_settings()
    if settings.llm_provider == "mock":
        raise RuntimeError(
            "Real run requires a non-mock LLM provider. Current LLM_PROVIDER=mock."
        )
    if not settings.openai_api_key:
        raise RuntimeError(
            "Real run requires OPENAI_API_KEY for the configured LLM provider. "
            "No mock fallback is allowed."
        )
    raise RuntimeError(
        "Real run final-answer execution is not wired in Week 5B repair; "
        "no simulated headline metrics will be produced."
    )


def _mode_name(*, mock_run: bool, retrieval_only: bool, real_run: bool) -> str:
    if mock_run:
        return "mock_smoke"
    if retrieval_only:
        return "retrieval_only"
    if real_run:
        return "real_ready_but_not_run"
    return "unknown"


def _uses_real_embedding(
    systems: list[str],
    retrieval_only: bool,
    unavailable_systems: dict[str, str],
) -> bool:
    if not retrieval_only:
        return False
    vector_systems = {"vector_only", "hybrid_rrf", "hybrid_rrf_rerank"}
    return bool((set(systems) - set(unavailable_systems)) & vector_systems)


def _uses_real_reranker(
    systems: list[str],
    retrieval_only: bool,
    unavailable_systems: dict[str, str],
) -> bool:
    if not retrieval_only:
        return False
    return "hybrid_rrf_rerank" in systems and "hybrid_rrf_rerank" not in unavailable_systems


def _make_run_id(split: EvalSplit) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{split.value}"


def _is_failure(result: EvalResult, case: EvalCase) -> bool:
    if result.grounded_correct is not None:
        return not result.grounded_correct
    if case.gold_doc_ids:
        return not bool(result.metrics.get("doc_hit@5"))
    return False


def _failure_reason(result: EvalResult, case: EvalCase) -> str:
    if result.grounded_correct is False:
        return "grounded_correctness_false"
    if case.gold_doc_ids and not result.metrics.get("doc_hit@5"):
        return "gold_doc_not_retrieved"
    return "none"
