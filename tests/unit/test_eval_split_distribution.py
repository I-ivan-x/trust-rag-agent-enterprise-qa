from collections import Counter

from app.eval.dataset import load_chunks_for_split, load_eval_cases


def test_external_split_distribution_and_negative_shapes() -> None:
    cases = load_eval_cases("external")
    by_type = Counter(case.query_type.value for case in cases)
    by_source = Counter(case.query_source.value for case in cases)

    assert len(cases) == 50
    assert by_source["real_user_question"] / len(cases) >= 0.5
    assert by_type["multi_doc_synthesis"] >= 4
    assert by_type["no_evidence_or_out_of_scope"] >= 4
    assert by_type["conflict_doc"] >= 2
    assert by_type["permission_denied"] >= 4
    assert by_type["deprecated_doc"] >= 2
    assert by_type["citation_required"] >= 4
    assert any(case.expected_behavior.value != "answer" for case in cases)

    chunk_doc_by_id = {}
    for split in ("external", "fixture"):
        chunk_doc_by_id.update(
            {chunk.chunk_id: chunk.doc_id for chunk in load_chunks_for_split(split)}
        )

    for case in cases:
        if case.query_type.value == "no_evidence_or_out_of_scope":
            assert case.gold_doc_ids == []
            assert case.gold_chunk_ids == []
            assert case.expected_response_mode.value == "refuse_no_evidence"
        if case.query_type.value == "conflict_doc":
            assert len(case.gold_doc_ids) >= 2
            assert len({chunk_doc_by_id[chunk_id] for chunk_id in case.gold_chunk_ids}) >= 2

