from __future__ import annotations

import json
from pathlib import Path

import app.eval.runner as runner
from tests.helpers import make_retrieved_chunk


def test_external_retrieval_ablation_summary_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    systems = ["vector_only", "bm25_only", "hybrid_rrf", "hybrid_rrf_rerank"]

    def fake_retrieve_baseline(system_name, query, chunks, *, top_k=10):
        del query, chunks, top_k
        return [
            make_retrieved_chunk(
                f"chunk-{system_name}",
                f"retrieval result from {system_name}",
                doc_id=f"doc-{system_name}",
            )
        ]

    monkeypatch.setattr(runner, "retrieve_baseline", fake_retrieve_baseline)

    summary = runner.run_eval(
        split="external",
        systems=systems,
        retrieval_only=True,
        output_root=tmp_path,
        run_id="external-retrieval-ablation",
        write_reports=False,
    )

    summary_path = tmp_path / "external-retrieval-ablation" / "summary.json"
    trace_path = tmp_path / "external-retrieval-ablation" / "traces.jsonl"
    loaded = json.loads(summary_path.read_text(encoding="utf-8"))
    trace_text = trace_path.read_text(encoding="utf-8")

    assert loaded == summary
    assert loaded["split"] == "external"
    assert loaded["mode"] == "retrieval_only"
    assert loaded["systems"] == systems
    assert loaded["num_cases"] == 50
    assert loaded["full_case_count"] == 50
    assert loaded["llm_call_count"] == 0
    assert loaded["mock_used"] is False
    assert loaded["toy_retrieval"] is False
    assert loaded["formal_retrieval_baseline"] is True
    assert loaded["expected_rewrite_used"] is False
    assert set(loaded["summary_metrics"]) == set(systems)
    for metrics in loaded["summary_metrics"].values():
        assert "hit@1" in metrics
        assert "hit@3" in metrics
        assert "hit@5" in metrics
        assert "mrr" in metrics
        assert "gold_doc_recall@5" in metrics
        assert "deprecated_confusion_rate" in metrics
    rendered = json.dumps(loaded, ensure_ascii=False) + trace_text
    assert "DEEPSEEK_API_KEY" not in rendered
    assert "sk-" not in rendered
