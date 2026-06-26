"""Q4-P7 tests for the run manifest (SPEC_Q4_P6_P7 §2)."""

from __future__ import annotations

import json

from app.eval.run_manifest import build_run_manifest, write_run_manifest

_INDEX_SUMMARY = {
    "chunks_loaded": 420,
    "chunks_path": "data/generated/ops_runbook/chunks.jsonl",
    "vector_count": 420,
    "keyword_count": 420,
    "qdrant_collection": "trust_rag_enterprise_qa",
}


def test_manifest_fields_complete() -> None:
    m = build_run_manifest(
        run_id="q4-p5-selection-calibrated",
        systems=["final_governed_rule", "final_governed_llm"],
        split="ops_test",
        k=3,
        mode="real",
        summary={"mock_used": False, "vector_unavailable": False, "reranker_unavailable": False},
        index_summary=_INDEX_SUMMARY,
        commit_sha="39d6cb7",
        cost={"llm_calls": 60, "total_tokens": None},
        latency_seconds=123.4,
        preregister_ref="Q4_P2_PREREGISTER@590aa1b",
    )
    for key in (
        "run_id", "created_at", "git_commit_sha", "split", "systems", "k", "mode",
        "model", "prompt_version", "controller_type", "retriever_index_fingerprint",
        "corpus_namespace", "seed", "mock_used", "vector_unavailable",
        "reranker_unavailable", "cost", "latency_seconds", "preregister_ref",
        "thresholds_snapshot",
    ):
        assert key in m, f"missing manifest field: {key}"

    assert m["git_commit_sha"] == "39d6cb7"
    assert m["mode"] == "real" and m["mock_used"] is False
    assert m["corpus_namespace"] == "ops_runbook"
    assert m["retriever_index_fingerprint"]["chunks_loaded"] == 420
    assert m["model"]["embedding"]["name"]  # populated from settings
    # thresholds are a read-only snapshot, never used in scoring
    assert m["thresholds_snapshot"]["AUTH_PRECISION_FLOOR"] == 0.6
    assert m["thresholds_snapshot"]["OVER_ESCALATION_CEIL"] == 0.3


def test_manifest_commit_sha_nonempty_by_default() -> None:
    m = build_run_manifest(
        run_id="r", systems=["final_governed_rule"], split="ops_dev", k=1, mode="real",
        summary={}, index_summary=_INDEX_SUMMARY,
    )
    assert m["git_commit_sha"]  # resolved from the repo


def test_manifest_reflects_mock_mode() -> None:
    m = build_run_manifest(
        run_id="r", systems=["final_governed_rule"], split=None, k=1, mode="mock",
        summary={"mock_used": True}, index_summary=None,
    )
    assert m["mode"] == "mock"
    assert m["mock_used"] is True
    assert m["retriever_index_fingerprint"]["chunks_loaded"] is None


def test_write_manifest(tmp_path) -> None:
    m = build_run_manifest(
        run_id="r", systems=["final_governed_rule"], split="ops_dev", k=1, mode="real",
        summary={}, index_summary=_INDEX_SUMMARY,
    )
    path = write_run_manifest(tmp_path, m)
    assert path.name == "manifest.json"
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["run_id"] == "r"
