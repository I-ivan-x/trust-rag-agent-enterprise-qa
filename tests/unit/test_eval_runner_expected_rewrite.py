from app.eval import runner
from app.schemas.eval import EvalCase
from tests.helpers import make_retrieved_chunk


def test_final_agentic_does_not_use_expected_rewrite(monkeypatch) -> None:
    captured_queries: list[str] = []

    def fake_retrieve(system_name, query, chunks, *, top_k=10):
        del system_name, chunks, top_k
        captured_queries.append(query)
        return [make_retrieved_chunk("other", "irrelevant", doc_id="doc-other")]

    monkeypatch.setattr(runner, "retrieve_toy_baseline", fake_retrieve)
    case = EvalCase(
        case_id="case-expected-rewrite",
        split="obfuscated",
        query="totally unrelated wording",
        query_type="fact_lookup",
        corpus_source="public_external",
        expected_behavior="answer",
        gold_doc_ids=["doc-gold"],
        gold_chunk_ids=["chunk-gold"],
        reference_claims=["gold claim"],
        expected_rewrite="gold answer query",
    )

    row = runner._run_case(
        case,
        "final_agentic",
        [],
        retrieval_only=False,
        mock_run=True,
    )

    assert captured_queries == ["totally unrelated wording"]
    assert row["trace"]["retrieval_query"] == "totally unrelated wording"
    assert row["trace"]["expected_rewrite"] == "gold answer query"
    assert row["trace"]["actual_rewritten_query"] is None
    assert "second_pass_improvement" not in row["result"].metrics


def test_final_agentic_rewrite_source_is_rule_based(monkeypatch) -> None:
    captured_queries: list[str] = []

    def fake_retrieve(system_name, query, chunks, *, top_k=10):
        del system_name, chunks, top_k
        captured_queries.append(query)
        return [make_retrieved_chunk("chunk-gold", "refresh token rate limit")]

    monkeypatch.setattr(runner, "retrieve_toy_baseline", fake_retrieve)
    case = EvalCase(
        case_id="case-rule-rewrite",
        split="obfuscated",
        query="refresh rlimit for auth?",
        query_type="fact_lookup",
        expected_behavior="answer",
        gold_doc_ids=["doc-test"],
        gold_chunk_ids=["chunk-gold"],
        reference_claims=["refresh token rate limit"],
        expected_rewrite="some gold-only query",
    )

    row = runner._run_case(
        case,
        "final_agentic",
        [],
        retrieval_only=False,
        mock_run=True,
    )

    assert captured_queries == [
        "refresh rlimit for auth?",
        "refresh token rate limit for auth?",
    ]
    assert row["trace"]["actual_rewritten_query"] == "refresh token rate limit for auth?"
    assert row["trace"]["rewrite_source"] == "rule_based_query_rewriter"
    assert row["trace"]["actual_rewritten_query"] != row["trace"]["expected_rewrite"]

