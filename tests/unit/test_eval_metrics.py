from app.eval.metrics import grounded_correctness, retrieval_metrics, summarize_results
from app.schemas.eval import EvalCase, EvalResult
from tests.helpers import make_retrieved_chunk


def test_retrieval_metrics_reports_hit_and_mrr() -> None:
    case = EvalCase(
        case_id="case-1",
        query="token lifetime",
        query_type="single_doc_fact",
        expected_behavior="answer",
        gold_doc_ids=["doc-auth"],
        gold_chunk_ids=["chunk-auth"],
    )
    retrieved = [
        make_retrieved_chunk("chunk-other", "unrelated", doc_id="doc-other", rank=1),
        make_retrieved_chunk("chunk-auth", "token lifetime is 30", doc_id="doc-auth", rank=2),
    ]

    metrics = retrieval_metrics(case, retrieved, k=5)

    assert metrics["hit@5"] is True
    assert metrics["doc_hit@5"] is True
    assert metrics["mrr"] == 0.5


def test_grounded_correctness_requires_valid_supporting_citation() -> None:
    assert grounded_correctness(
        raw_correct=True,
        citation_valid=True,
        supports_core_claim=True,
    )
    assert not grounded_correctness(
        raw_correct=True,
        citation_valid=False,
        supports_core_claim=True,
    )


def test_summarize_results_groups_by_system() -> None:
    result = EvalResult(
        case_id="case-1",
        system_name="hybrid_rrf",
        eval_split="fixture",
        corpus_source="synthetic_fixture",
        raw_correct=True,
        grounded_correct=True,
        citation_valid=True,
        refused=False,
        metrics={"hit@5": True, "mrr": 1.0},
    )

    summary = summarize_results([result])

    assert summary["hybrid_rrf"]["hit@5"] == 1.0
    assert summary["hybrid_rrf"]["grounded_correctness"] == 1.0

