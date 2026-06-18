from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.enums import DecisionReason, EvalSplit, ExpectedBehavior
from app.eval.agent_attribution import compute_agent_attribution
from app.eval.baselines import BaselineUnavailable, retrieve_baseline, retrieve_toy_baseline
from app.eval.citation_audit import verify_citations
from app.eval.dataset import load_chunks_for_split, load_eval_cases, terms, write_jsonl
from app.eval.metrics import grounded_correctness, retrieval_metrics, summarize_results
from app.eval.real_pipeline import (
    RealFinalResult,
    run_direct_llm_baseline,
    run_real_final_pipeline,
)
from app.eval.report import (
    write_citation_audit_doc,
    write_eval_report,
    write_failure_analysis,
)
from app.guards.evidence_gate import EvidenceGateConfig, evidence_gate_config_from_settings
from app.index.build_index import INDEX_METADATA_PATH, read_index_metadata
from app.llm.usage import get_usage_tracker
from app.observability.tracing import make_trace_event, now_iso
from app.retrieval.query_rewriter import rewrite_query_for_evidence
from app.schemas.citation import Citation, CitationLocator
from app.schemas.eval import EvalCase, EvalResult, EvalRunSummary
from app.schemas.retrieval import RetrievedChunk

RETRIEVAL_SYSTEMS = {"vector_only", "bm25_only", "hybrid_rrf", "hybrid_rrf_rerank"}
FINAL_SYSTEMS = {
    "final_gated",
    "final_gated_calibrated",
    "final_agentic",
    "final_agentic_v2",
    "final_agentic_v2_llm",
}
BASELINE_LLM_SYSTEMS = {"direct_llm"}


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
    limit: int | None = None,
    case_id: str | None = None,
    max_cases: int | None = None,
    sleep_seconds: float = 0.0,
    max_output_tokens: int | None = None,
    evidence_gate_config: EvidenceGateConfig | None = None,
    trust_gate_policy: str | None = None,
) -> dict[str, Any]:
    eval_split = EvalSplit(split)
    _validate_mode(systems, mock_run=mock_run, retrieval_only=retrieval_only, real_run=real_run)
    if real_run:
        _require_real_run_ready(systems)

    selected_run_id = run_id or _make_run_id(eval_split)
    run_dir = (output_root or get_settings().eval_runs_dir) / selected_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    resolved_evidence_gate_config = (
        evidence_gate_config or evidence_gate_config_from_settings(get_settings())
    )
    resolved_trust_gate_policy = trust_gate_policy or getattr(
        get_settings(),
        "trust_gate_policy",
        "legacy",
    )

    all_cases = load_eval_cases(eval_split)
    case_selection = {
        "limit": limit,
        "case_id": case_id,
        "max_cases": max_cases,
    }
    cases = _select_cases(
        all_cases,
        case_id=case_id,
        limit=limit,
        max_cases=max_cases,
    )
    get_usage_tracker().reset()
    chunks = load_chunks_for_split(eval_split)
    results: list[EvalResult] = []
    result_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    answer_rows: list[dict[str, Any]] = []
    unavailable_systems: dict[str, str] = {}
    reranker_unavailable_any = False
    vector_unavailable_any = False

    for system_name in systems:
        for case in cases:
            try:
                row = _run_case(
                    case,
                    system_name,
                    chunks,
                    retrieval_only=retrieval_only,
                    mock_run=mock_run,
                    real_run=real_run,
                    run_id=selected_run_id,
                    max_output_tokens=max_output_tokens,
                    evidence_gate_config=resolved_evidence_gate_config,
                    trust_gate_policy=resolved_trust_gate_policy,
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
            if row["answer"] is not None:
                answer_rows.append(row["answer"])
            if row.get("reranker_unavailable"):
                reranker_unavailable_any = True
            if row.get("vector_unavailable"):
                vector_unavailable_any = True
            if _is_failure(result, case):
                failure_rows.append(row["failure"])
            if real_run and sleep_seconds > 0:
                time.sleep(sleep_seconds)

    summary = _build_summary(
        run_id=selected_run_id,
        systems=systems,
        eval_split=eval_split,
        cases=cases,
        results=results,
        trace_rows=trace_rows,
        audit_rows=audit_rows,
        unavailable_systems=unavailable_systems,
        full_case_count=len(all_cases),
        case_selection=case_selection,
        mock_run=mock_run,
        retrieval_only=retrieval_only,
        real_run=real_run,
        reranker_unavailable_any=reranker_unavailable_any,
        vector_unavailable_any=vector_unavailable_any,
        run_dir=run_dir,
        usage=get_usage_tracker().totals,
        evidence_gate_config=resolved_evidence_gate_config,
        trust_gate_policy=resolved_trust_gate_policy,
    )

    write_jsonl(run_dir / "results.jsonl", result_rows)
    write_jsonl(run_dir / "traces.jsonl", trace_rows)
    write_jsonl(run_dir / "failures.jsonl", failure_rows)
    write_jsonl(run_dir / "citation_audit_sample.jsonl", audit_rows[:25])
    write_jsonl(run_dir / "answers.jsonl", answer_rows)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if write_reports:
        write_eval_report(Path("docs/EVALUATION_REPORT.md"), summary)
        write_failure_analysis(Path("docs/FAILURE_ANALYSIS.md"), failure_rows)
        write_citation_audit_doc(Path("docs/CITATION_AUDIT.md"), audit_rows[:25])
    return summary


def _select_cases(
    cases: list[EvalCase],
    *,
    case_id: str | None,
    limit: int | None,
    max_cases: int | None,
) -> list[EvalCase]:
    if case_id:
        cases = [case for case in cases if case.case_id == case_id]
        if not cases:
            raise ValueError(f"case_id not found in split: {case_id}")
    caps = [value for value in (limit, max_cases) if value is not None and value >= 0]
    if caps:
        cases = cases[: min(caps)]
    return cases


def _run_case(
    case: EvalCase,
    system_name: str,
    chunks: list[Any],
    *,
    retrieval_only: bool,
    mock_run: bool,
    real_run: bool = False,
    run_id: str = "unknown",
    max_output_tokens: int | None = None,
    evidence_gate_config: EvidenceGateConfig | None = None,
    trust_gate_policy: str | None = None,
) -> dict[str, Any]:
    if real_run:
        return _run_case_real(
            case,
            system_name,
            run_id=run_id,
            max_output_tokens=max_output_tokens,
            evidence_gate_config=evidence_gate_config,
            trust_gate_policy=trust_gate_policy,
        )
    return _run_case_offline(
        case, system_name, chunks, retrieval_only=retrieval_only, mock_run=mock_run
    )


def _run_case_offline(
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
            expected_rewrite_present=case.expected_rewrite is not None,
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
                "mock_answer",
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
    trace = _trace_row(
        trace_id=trace_id,
        case=case,
        system_name=system_name,
        retrieval_query=retrieval_query,
        actual_rewritten_query=actual_rewritten_query,
        rewrite_source=rewrite_source,
        rewrite_model_name=None,
        retrieved=retrieved,
        events=trace_events,
    )
    return {
        "result": result,
        "trace": trace,
        "audit": audit_payload,
        "answer": None,
        "failure": _failure_row(case, system_name, result),
    }


def _run_case_real(
    case: EvalCase,
    system_name: str,
    *,
    run_id: str,
    max_output_tokens: int | None,
    evidence_gate_config: EvidenceGateConfig | None,
    trust_gate_policy: str | None,
) -> dict[str, Any]:
    trace_id = f"trace-{case.case_id}-{system_name}"
    tracker = get_usage_tracker()
    answer_before, rewrite_before = tracker.snapshot()
    if system_name == "direct_llm":
        real = run_direct_llm_baseline(case, max_output_tokens=max_output_tokens)
    else:
        real = run_real_final_pipeline(
            case,
            system_name,
            max_output_tokens=max_output_tokens,
            evidence_gate_config=evidence_gate_config,
            trust_gate_policy=trust_gate_policy,
        )
    answer_after, rewrite_after = tracker.snapshot()
    answer_llm_called = answer_after > answer_before
    rewrite_llm_called = rewrite_after > rewrite_before

    metrics = retrieval_metrics(case, real.reranked_chunks, k=5)
    if real.first_pass_reranked is not None:
        first_pass_metrics = retrieval_metrics(case, real.first_pass_reranked, k=5)
        metrics["first_pass_doc_hit@5"] = first_pass_metrics["doc_hit@5"]
        metrics["second_pass_improvement"] = bool(
            metrics["doc_hit@5"] and not first_pass_metrics["doc_hit@5"]
        )

    raw_correct = _score_raw_correct(case, real)
    audit = verify_citations(
        claims=case.reference_claims,
        citations=real.citations,
        retrieved_chunks=real.reranked_chunks,
    )
    if real.refused:
        # A correct trust-gated refusal is not penalized for lacking citations.
        citation_valid: bool = True
        supports_core_claim = True
    else:
        citation_valid = audit.citation_valid if case.requires_citation else True
        supports_core_claim = audit.supports_core_claim or not case.requires_citation
    grounded = grounded_correctness(
        raw_correct=raw_correct,
        citation_valid=citation_valid,
        supports_core_claim=supports_core_claim,
    )
    metrics.update(
        {
            "citation_valid": citation_valid,
            "supports_core_claim": supports_core_claim,
            "grounded_correct": grounded,
            "unsupported_claim_rate": not supports_core_claim,
            "refusal_accuracy": _refusal_accuracy(case, real.refused),
            "false_refusal_rate": _false_refusal(case, real.refused),
            "false_answer_rate": _false_answer(case, real.refused),
        }
    )

    audit_payload = {
        "case_id": case.case_id,
        "system_name": system_name,
        **audit.model_dump(mode="json"),
    }

    events = [
        make_trace_event("load_case", case_id=case.case_id, system_name=system_name),
        make_trace_event(
            "rewrite",
            expected_rewrite_present=case.expected_rewrite is not None,
            expected_rewrite_policy="informational_only",
            actual_rewritten_query=real.actual_rewritten_query,
            rewrite_source=real.rewrite_source,
            rewrite_model_name=real.rewrite_model_name,
            rewrite_reason=real.rewrite_reason,
            second_pass_attempted=real.second_pass_attempted,
        ),
        make_trace_event(
            "answer",
            refused=real.refused,
            decision_reason=real.decision_reason.value,
            response_mode=real.response_mode.value,
            used_real_llm_answer=real.used_real_llm_answer,
            answer_llm_called=answer_llm_called,
            rewrite_llm_called=rewrite_llm_called,
            llm_provider=get_settings().llm_provider,
            llm_model_name=get_settings().llm_model_name,
            rewrite_model_name=real.rewrite_model_name,
            expected_rewrite_used=False,
        ),
    ]

    result = EvalResult(
        case_id=case.case_id,
        system_name=system_name,
        eval_split=case.eval_split,
        corpus_source=case.corpus_source,
        raw_correct=raw_correct,
        grounded_correct=grounded,
        citation_valid=citation_valid,
        refused=real.refused,
        decision_reason=real.decision_reason,
        rewrite_triggered=real.actual_rewritten_query is not None,
        trace_id=trace_id,
        metrics=metrics,
        errors=[w for w in real.warnings if "error" in w.lower()],
    )
    trace = _trace_row(
        trace_id=trace_id,
        case=case,
        system_name=system_name,
        retrieval_query=real.actual_rewritten_query or case.query,
        actual_rewritten_query=real.actual_rewritten_query,
        rewrite_source=real.rewrite_source,
        rewrite_model_name=real.rewrite_model_name,
        retrieved=real.reranked_chunks,
        events=events,
    )
    if real.agent_trace:
        trace.update(real.agent_trace)
    answer_row = _answer_row(
        run_id=run_id,
        case=case,
        system_name=system_name,
        real=real,
    )
    return {
        "result": result,
        "trace": trace,
        "audit": audit_payload,
        "answer": answer_row,
        "failure": _failure_row(case, system_name, result),
        "reranker_unavailable": real.reranker_unavailable,
        "vector_unavailable": _vector_unavailable(real.warnings),
    }


def _answer_row(
    *,
    run_id: str,
    case: EvalCase,
    system_name: str,
    real: RealFinalResult,
) -> dict[str, Any]:
    chunk_texts_by_id = {
        item.chunk.chunk_id: item.chunk.text for item in real.reranked_chunks
    }
    cited_chunk_texts: dict[str, str | None] = {}
    cited_text_sha256: dict[str, str | None] = {}
    warnings = list(real.warnings)

    for citation in real.citations:
        chunk_id = citation.chunk_id
        text = chunk_texts_by_id.get(chunk_id)
        cited_chunk_texts[chunk_id] = text
        cited_text_sha256[chunk_id] = (
            sha256(text.encode("utf-8")).hexdigest() if text is not None else None
        )
        if text is None:
            warnings.append(f"cited_chunk_not_in_reranked:{chunk_id}")

    return {
        "run_id": run_id,
        "case_id": case.case_id,
        "system_name": system_name,
        "eval_split": case.eval_split.value,
        "refused": real.refused,
        "response_mode": real.response_mode.value,
        "answer_text": real.answer_text,
        "llm_model_name": get_settings().llm_model_name,
        "claims": [claim.model_dump(mode="json") for claim in real.claims],
        "citations": [
            citation.model_dump(mode="json") for citation in real.citations
        ],
        "gate_decisions": real.gate_decisions,
        "agent_trace": real.agent_trace,
        "cited_chunk_texts": cited_chunk_texts,
        "cited_text_sha256": cited_text_sha256,
        "warnings": warnings,
    }


def _score_raw_correct(case: EvalCase, real: RealFinalResult) -> bool:
    expected = case.expected_behavior
    mode = real.response_mode
    if expected in {
        ExpectedBehavior.refuse_no_evidence,
        ExpectedBehavior.refuse_permission,
        ExpectedBehavior.warn_deprecated,
        ExpectedBehavior.report_conflict,
    }:
        return mode == expected
    if real.refused:
        return False
    return _answer_overlaps_reference(real.answer_text, case)


def _vector_unavailable(warnings: list[str]) -> bool:
    return any("Vector retrieval unavailable" in warning for warning in warnings)


def _answer_overlaps_reference(answer_text: str, case: EvalCase) -> bool:
    references = list(case.reference_claims)
    if case.reference_answer:
        references.append(case.reference_answer)
    references = [ref for ref in references if ref and ref.strip()]
    if not references:
        # No offline reference is available; treat any non-empty answer as raw-correct.
        return bool(answer_text.strip())
    answer_terms = set(terms(answer_text))
    if not answer_terms:
        return False
    for reference in references:
        ref_terms = set(terms(reference))
        if not ref_terms:
            continue
        overlap = len(answer_terms & ref_terms) / len(ref_terms)
        if overlap >= 0.34:
            return True
    return False


def _expected_refusal(case: EvalCase) -> bool:
    return case.expected_behavior in {
        ExpectedBehavior.refuse_no_evidence,
        ExpectedBehavior.refuse_permission,
    }


def _refusal_accuracy(case: EvalCase, refused: bool) -> bool:
    return refused == _expected_refusal(case)


def _false_refusal(case: EvalCase, refused: bool) -> bool:
    return refused and not _expected_refusal(case)


def _false_answer(case: EvalCase, refused: bool) -> bool:
    return (not refused) and _expected_refusal(case)


def _trace_row(
    *,
    trace_id: str,
    case: EvalCase,
    system_name: str,
    retrieval_query: str,
    actual_rewritten_query: str | None,
    rewrite_source: str,
    rewrite_model_name: str | None,
    retrieved: list[RetrievedChunk],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "run_at": now_iso(),
        "case_id": case.case_id,
        "split": case.eval_split.value,
        "system_name": system_name,
        "query": case.query,
        "retrieval_query": retrieval_query,
        "expected_rewrite": case.expected_rewrite,
        "expected_rewrite_present": case.expected_rewrite is not None,
        "expected_rewrite_policy": "informational_only",
        "actual_rewritten_query": actual_rewritten_query,
        "rewrite_source": rewrite_source,
        "rewrite_model_name": rewrite_model_name,
        "retrieved_chunk_ids": [item.chunk.chunk_id for item in retrieved[:10]],
        "retrieved_doc_ids": [item.chunk.doc_id for item in retrieved[:10]],
        "events": events,
    }


def _failure_row(case: EvalCase, system_name: str, result: EvalResult) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "system_name": system_name,
        "query": case.query,
        "reason": _failure_reason(result, case),
        "metrics": result.metrics,
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
    unknown = set(systems) - RETRIEVAL_SYSTEMS - FINAL_SYSTEMS - BASELINE_LLM_SYSTEMS
    if unknown:
        raise ValueError(f"Unsupported systems: {', '.join(sorted(unknown))}")
    selected_modes = sum([mock_run, retrieval_only, real_run])
    if selected_modes != 1:
        raise ValueError("Select exactly one mode: --mock-run, --retrieval-only, or --real-run")
    if retrieval_only and any(
        system in FINAL_SYSTEMS or system in BASELINE_LLM_SYSTEMS for system in systems
    ):
        raise ValueError("final_* and direct_llm systems require --mock-run or --real-run")
    if not retrieval_only and any(system in RETRIEVAL_SYSTEMS for system in systems):
        raise ValueError("retrieval baseline systems require --retrieval-only")
    if not real_run and any(system in BASELINE_LLM_SYSTEMS for system in systems):
        raise ValueError("direct_llm baseline requires --real-run (it calls the real LLM).")


def _require_real_run_ready(systems: list[str]) -> None:
    settings = get_settings()
    if settings.llm_provider.lower() == "mock":
        raise RuntimeError(
            "Real run requires a non-mock LLM provider. Current LLM_PROVIDER=mock."
        )
    if not _llm_api_key(settings):
        raise RuntimeError(
            f"Real run requires an API key for LLM_PROVIDER={settings.llm_provider}. "
            "No mock fallback is allowed."
        )
    if any(system in FINAL_SYSTEMS for system in systems):
        metadata = read_index_metadata(INDEX_METADATA_PATH)
        if metadata is None:
            raise RuntimeError(
                "Real run with final_* systems requires a built retrieval index. "
                "Run scripts/rebuild_indexes.py first."
            )
        if str(metadata.get("embedding_provider")) == "mock":
            raise RuntimeError(
                "Real run cannot claim real embeddings: current index uses mock embeddings."
            )


def _llm_api_key(settings) -> str | None:
    if settings.llm_provider.lower() == "deepseek":
        return settings.deepseek_api_key
    return settings.openai_api_key


def _build_summary(
    *,
    run_id: str,
    systems: list[str],
    eval_split: EvalSplit,
    cases: list[EvalCase],
    results: list[EvalResult],
    trace_rows: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]],
    unavailable_systems: dict[str, str],
    full_case_count: int,
    case_selection: dict[str, Any],
    mock_run: bool,
    retrieval_only: bool,
    real_run: bool,
    reranker_unavailable_any: bool,
    run_dir: Path,
    usage,
    vector_unavailable_any: bool = False,
    evidence_gate_config: EvidenceGateConfig | None = None,
    trust_gate_policy: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    has_final = bool((set(systems) - set(unavailable_systems)) & FINAL_SYSTEMS)
    selection_limited = any(case_selection.get(key) is not None for key in case_selection)
    full_split_run = bool(
        not selection_limited
        and len(cases) == full_case_count
        and full_case_count > 0
    )
    pilot_run = not full_split_run
    redteam_run = eval_split is EvalSplit.redteam

    uses_real_embedding = _uses_real_embedding(
        systems, retrieval_only, real_run, unavailable_systems
    )
    uses_real_reranker = _uses_real_reranker(
        systems,
        retrieval_only=retrieval_only,
        real_run=real_run,
        unavailable_systems=unavailable_systems,
        reranker_unavailable_any=reranker_unavailable_any,
    )
    uses_real_llm = bool(real_run and settings.llm_provider.lower() != "mock")
    resolved_evidence_gate_config = (
        evidence_gate_config or evidence_gate_config_from_settings(settings)
    )
    resolved_trust_gate_policy = trust_gate_policy or getattr(
        settings,
        "trust_gate_policy",
        "legacy",
    )

    summary = EvalRunSummary(
        run_id=run_id,
        systems=systems,
        eval_split=eval_split,
        num_cases=len(cases),
        summary_metrics=summarize_results(results),
        uses_real_embedding=uses_real_embedding,
        uses_real_reranker=uses_real_reranker,
        uses_real_llm=uses_real_llm,
    ).model_dump(mode="json")

    final_headline_eligible = bool(
        not redteam_run
        and real_run
        and has_final
        and full_split_run
        and uses_real_llm
        and uses_real_embedding
        and (uses_real_reranker or reranker_unavailable_any)
        and not mock_run
        and not unavailable_systems
        and bool(trace_rows)
        and bool(audit_rows)
        and usage.total_calls > 0
        and not vector_unavailable_any
    )
    retrieval_headline_eligible = bool(
        not redteam_run
        and retrieval_only
        and full_split_run
        and not mock_run
        and bool(results)
        and bool(trace_rows)
        and not unavailable_systems
        and _retrieval_stack_is_real(systems, uses_real_embedding)
    )
    headline_eligible = final_headline_eligible or retrieval_headline_eligible
    if redteam_run:
        headline_scope = "redteam"
    else:
        headline_scope = "smoke" if mock_run else ("pilot" if pilot_run else "full_split")
    pilot_eligible = bool(
        not redteam_run
        and pilot_run
        and not mock_run
        and (retrieval_only or usage.total_calls > 0)
    )

    summary.update(
        {
            "split": eval_split.value,
            "mode": _mode_name(mock_run=mock_run, retrieval_only=retrieval_only, real_run=real_run),
            "headline_eligible": headline_eligible,
            "headline_scope": headline_scope,
            "redteam_run": redteam_run,
            "pilot_eligible": pilot_eligible,
            "full_split_run": full_split_run,
            "full_case_count": full_case_count,
            "case_selection": case_selection,
            "llm_provider": settings.llm_provider if real_run else None,
            "llm_model_name": settings.llm_model_name if real_run else None,
            "rewrite_llm_provider": settings.rewrite_llm_provider if real_run else None,
            "rewrite_llm_model_name": (
                settings.rewrite_llm_model_name if real_run else None
            ),
            "evidence_gate_config": resolved_evidence_gate_config.model_dump(mode="json"),
            "trust_gate_policy": resolved_trust_gate_policy,
            "uses_real_llm": uses_real_llm,
            "uses_real_embedding": uses_real_embedding,
            "uses_real_reranker": uses_real_reranker,
            "reranker_unavailable": bool(real_run and reranker_unavailable_any),
            "vector_unavailable": bool(real_run and vector_unavailable_any),
            "llm_call_count": usage.total_calls,
            "answer_llm_call_count": usage.answer_calls,
            "rewrite_llm_call_count": usage.rewrite_calls,
            "llm_usage_prompt_tokens": usage.prompt_tokens,
            "llm_usage_completion_tokens": usage.completion_tokens,
            "llm_usage_total_tokens": usage.total_tokens,
            "llm_usage_reported": usage.usage_reported,
            "real_llm_invoked": bool(real_run and usage.total_calls > 0),
            "real_run_call_warning": (
                "Real run made zero real LLM calls; this is NOT a completed real LLM eval."
                if real_run and usage.total_calls == 0
                else None
            ),
            "expected_rewrite_used": False,
            "mock_used": bool(mock_run),
            "toy_retrieval": bool(mock_run),
            "formal_retrieval_baseline": bool(retrieval_only),
            "unavailable_systems": unavailable_systems,
            "expected_rewrite_policy": (
                "expected_rewrite is informational only and is never used for "
                "retrieval or scoring."
            ),
            "pilot_run_note": (
                "Pilot run: report as evidence of pipeline validity, not final headline metrics."
                if pilot_run and not mock_run
                else None
            ),
            "mock_run_note": (
                "Mock/simulated eval runs use toy retrieval smoke only and must not "
                "be used as headline metrics."
                if mock_run
                else None
            ),
            "redteam_headline_policy": (
                "Red-team injection runs may be cited as defensive red-team evidence "
                "but must never be merged into external headline metrics."
                if redteam_run
                else None
            ),
            "run_dir": run_dir.as_posix(),
        }
    )
    agent_attribution = compute_agent_attribution(trace_rows, results)
    if agent_attribution is not None:
        summary["agent_attribution"] = agent_attribution
    return summary


def _mode_name(*, mock_run: bool, retrieval_only: bool, real_run: bool) -> str:
    if mock_run:
        return "mock_smoke"
    if retrieval_only:
        return "retrieval_only"
    if real_run:
        return "real_run"
    return "unknown"


def _uses_real_embedding(
    systems: list[str],
    retrieval_only: bool,
    real_run: bool,
    unavailable_systems: dict[str, str],
) -> bool:
    available = set(systems) - set(unavailable_systems)
    if retrieval_only:
        vector_systems = {"vector_only", "hybrid_rrf", "hybrid_rrf_rerank"}
        return bool(available & vector_systems)
    if real_run:
        return bool(available & FINAL_SYSTEMS)
    return False


def _uses_real_reranker(
    systems: list[str],
    *,
    retrieval_only: bool,
    real_run: bool,
    unavailable_systems: dict[str, str],
    reranker_unavailable_any: bool,
) -> bool:
    available = set(systems) - set(unavailable_systems)
    if retrieval_only:
        return "hybrid_rrf_rerank" in available
    if real_run:
        settings = get_settings()
        return bool(
            available & FINAL_SYSTEMS
            and settings.reranker_provider.lower() != "mock"
            and not reranker_unavailable_any
        )
    return False


def _retrieval_stack_is_real(systems: list[str], uses_real_embedding: bool) -> bool:
    selected = set(systems)
    if not selected <= RETRIEVAL_SYSTEMS:
        return False
    if selected == {"bm25_only"}:
        return True
    if selected & {"vector_only", "hybrid_rrf", "hybrid_rrf_rerank"}:
        return uses_real_embedding
    return False


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
