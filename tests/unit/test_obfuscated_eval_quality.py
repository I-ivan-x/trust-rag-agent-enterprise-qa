from app.eval.dataset import load_chunks_for_split, load_eval_cases


def test_obfuscated_eval_queries_are_realistic_and_grounded() -> None:
    cases = load_eval_cases("obfuscated")
    chunk_ids = {chunk.chunk_id for chunk in load_chunks_for_split("obfuscated")}

    assert len(cases) == 15
    for case in cases:
        assert "Need the FastAPI bit for case" not in case.query
        assert len(case.query) >= 30
        assert case.derived_from_case_id
        assert case.gold_doc_ids
        assert case.gold_chunk_ids
        assert set(case.gold_chunk_ids) <= chunk_ids
        assert case.expected_rewrite
        assert case.query != case.expected_rewrite
        assert "informational only" in (case.notes or "")

