from pathlib import Path

from app.core.enums import EvalSplit
from app.eval.dataset import load_eval_cases, title_overlap_score, write_eval_cases
from app.schemas.eval import EvalCase


def test_eval_case_accepts_split_alias_and_writes_week5b_shape(tmp_path: Path) -> None:
    case = EvalCase(
        case_id="external-test",
        split="external",
        query="How do I upload a file?",
        query_type="fact_lookup",
        corpus_source="public_external",
        expected_behavior="answer",
        gold_doc_ids=["doc-public"],
        gold_chunk_ids=["chunk-public"],
        reference_claims=["Files can be uploaded."],
        requires_citation=True,
    )

    path = tmp_path / "external_eval.jsonl"
    write_eval_cases(path, [case])
    payload = path.read_text(encoding="utf-8")

    assert '"split": "external"' in payload
    assert "eval_split" not in payload
    loaded = load_eval_cases(input_path=path)
    assert loaded[0].eval_split is EvalSplit.external
    assert loaded[0].must_cite is True


def test_title_overlap_score_ignores_stopwords() -> None:
    score = title_overlap_score(
        "How can I enable CORS in FastAPI?",
        ["CORS (Cross-Origin Resource Sharing)"],
    )

    assert 0 < score < 0.6

