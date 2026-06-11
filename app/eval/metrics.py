from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.core.enums import ExpectedBehavior
from app.schemas.eval import EvalCase, EvalResult
from app.schemas.retrieval import RetrievedChunk


def retrieval_metrics(
    case: EvalCase,
    retrieved: list[RetrievedChunk],
    *,
    k: int = 5,
) -> dict[str, Any]:
    top = retrieved[:k]
    gold_chunks = set(case.gold_chunk_ids)
    gold_docs = set(case.gold_doc_ids)
    retrieved_chunk_ids = [item.chunk.chunk_id for item in top]
    retrieved_doc_ids = [item.chunk.doc_id for item in top]

    hit = bool(gold_chunks & set(retrieved_chunk_ids)) if gold_chunks else False
    doc_hit = bool(gold_docs & set(retrieved_doc_ids)) if gold_docs else False
    mrr = 0.0
    for rank, item in enumerate(top, 1):
        if item.chunk.chunk_id in gold_chunks or item.chunk.doc_id in gold_docs:
            mrr = 1.0 / rank
            break
    doc_recall = 0.0
    if gold_docs:
        doc_recall = len(gold_docs & set(retrieved_doc_ids)) / len(gold_docs)

    return {
        f"hit@{k}": hit,
        f"doc_hit@{k}": doc_hit,
        "mrr": round(mrr, 4),
        "doc_recall": round(doc_recall, 4),
        "hard_negative_error": _hard_negative_error(case, retrieved_doc_ids),
        "deprecated_confusion": _deprecated_confusion(case, top),
    }


def grounded_correctness(
    *,
    raw_correct: bool,
    citation_valid: bool,
    supports_core_claim: bool,
) -> bool:
    return raw_correct and citation_valid and supports_core_claim


def summarize_results(results: list[EvalResult]) -> dict[str, Any]:
    by_system: dict[str, list[EvalResult]] = defaultdict(list)
    for result in results:
        by_system[result.system_name].append(result)

    summary: dict[str, Any] = {}
    for system_name, system_results in sorted(by_system.items()):
        summary[system_name] = _summarize_system(system_results)
    return summary


def _summarize_system(results: list[EvalResult]) -> dict[str, Any]:
    count = len(results)
    metric_totals: dict[str, float] = defaultdict(float)
    metric_counts: dict[str, int] = defaultdict(int)
    for result in results:
        for name, value in result.metrics.items():
            if isinstance(value, bool):
                metric_totals[name] += 1.0 if value else 0.0
                metric_counts[name] += 1
            elif isinstance(value, int | float):
                metric_totals[name] += float(value)
                metric_counts[name] += 1

    aggregate = {
        name: round(metric_totals[name] / metric_counts[name], 4)
        for name in sorted(metric_totals)
        if metric_counts[name]
    }
    aggregate["cases"] = count
    aggregate["refusal_rate"] = round(
        sum(1 for result in results if result.refused) / count,
        4,
    ) if count else 0.0
    raw_values = [result.raw_correct for result in results if result.raw_correct is not None]
    grounded_values = [
        result.grounded_correct for result in results if result.grounded_correct is not None
    ]
    if raw_values:
        aggregate["raw_correctness"] = round(sum(raw_values) / len(raw_values), 4)
    if grounded_values:
        aggregate["grounded_correctness"] = round(
            sum(grounded_values) / len(grounded_values),
            4,
        )
    return aggregate


def _hard_negative_error(case: EvalCase, retrieved_doc_ids: list[str]) -> bool:
    if case.query_type.value != "hard_negative" or not case.gold_doc_ids:
        return False
    first_retrieved = retrieved_doc_ids[0] if retrieved_doc_ids else None
    return first_retrieved is not None and first_retrieved not in set(case.gold_doc_ids)


def _deprecated_confusion(case: EvalCase, retrieved: list[RetrievedChunk]) -> bool:
    if case.expected_behavior is ExpectedBehavior.warn_deprecated:
        return False
    return any(item.chunk.status.value == "deprecated" for item in retrieved)
