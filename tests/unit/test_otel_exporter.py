"""Q4-P6 tests for the OpenInference/OTel trace exporter (SPEC_Q4_P6_P7 §1.4).

Uses an in-memory span exporter only -- no OTLP backend, no network. Skipped entirely
when the optional 'otel' dependency is not installed, so the project stays green without it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("opentelemetry.sdk.trace")

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability.otel_exporter import SPAN_KIND, export_run_to_otel


def _write_traces(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _rule_row() -> dict:
    return {
        "case_id": "ora-001",
        "system_name": "final_governed_rule",
        "run_index": 1,
        "split": "ops_test",
        "retrieved_chunk_ids": ["doc-a::chunk-0", "doc-b::chunk-1"],
        "blocked_chunk_ids": ["doc-restricted::chunk-0"],
        "approval_state": "committed",
        "sink_record_id": "flag_stale-abc123",
        "governance_trace": {
            "controller_source": "rule",
            "proposed_action": "flag_stale",
            "risk_tier": "auto",
            "validator_verdict": "accepted",
            "validator_reject_reason": None,
        },
        "result_contract": {
            "evidence_decision": "sufficient",
            "validator_ok": True,
            "forced_action": None,
            "proposed_action": "flag_stale",
            "risk_tier": "auto",
        },
    }


def _llm_row() -> dict:
    row = _rule_row()
    row["system_name"] = "final_governed_llm"
    row["governance_trace"]["controller_source"] = "llm"
    row["result_contract"]["controller_source"] = "llm"
    return row


def _kinds(exporter: InMemorySpanExporter) -> list[str]:
    return [s.attributes.get(SPAN_KIND) for s in exporter.get_finished_spans()]


def _span(exporter: InMemorySpanExporter, name: str):
    for s in exporter.get_finished_spans():
        if s.name == name:
            return s
    raise AssertionError(f"span {name!r} not found")


def test_span_kinds_mapped(tmp_path: Path) -> None:
    traces = _write_traces(tmp_path / "traces.jsonl", [_rule_row()])
    exporter = InMemorySpanExporter()
    n = export_run_to_otel(traces, exporter=exporter, commit_sha="deadbeef")

    kinds = _kinds(exporter)
    assert n == len(exporter.get_finished_spans())
    assert kinds.count("RETRIEVER") == 1
    assert kinds.count("RERANKER") == 1
    assert kinds.count("GUARDRAIL") == 4  # acl, document_state, evidence, validator
    assert kinds.count("AGENT") == 2  # case root + controller
    assert kinds.count("TOOL") == 1


def test_required_attr_present(tmp_path: Path) -> None:
    traces = _write_traces(tmp_path / "traces.jsonl", [_rule_row()])
    exporter = InMemorySpanExporter()
    export_run_to_otel(traces, exporter=exporter, commit_sha="deadbeef")

    for span in exporter.get_finished_spans():
        assert span.attributes.get(SPAN_KIND), f"{span.name} missing {SPAN_KIND}"

    root = _span(exporter, "governance.case")
    assert root.attributes["gen_ai.agent.name"] == "trustrag-ops-governor"
    assert root.attributes["gen_ai.agent.id"] == "final_governed_rule"
    assert root.attributes["gen_ai.agent.version"] == "deadbeef"


def test_tool_span_action_attrs(tmp_path: Path) -> None:
    traces = _write_traces(tmp_path / "traces.jsonl", [_rule_row()])
    exporter = InMemorySpanExporter()
    export_run_to_otel(traces, exporter=exporter)

    action = _span(exporter, "action")
    assert action.attributes[SPAN_KIND] == "TOOL"
    assert action.attributes["tool.name"] == "flag_stale"
    assert action.attributes["action.risk_tier"] == "auto"
    assert action.attributes["action.approval_state"] == "committed"
    assert action.attributes["action.sink_record_id"] == "flag_stale-abc123"


def test_llm_controller_nested_llm_span(tmp_path: Path) -> None:
    traces = _write_traces(tmp_path / "traces.jsonl", [_llm_row()])
    exporter = InMemorySpanExporter()
    export_run_to_otel(traces, exporter=exporter, llm_provider="xiaomi", llm_model="mimo-v2.5-pro")

    assert "LLM" in _kinds(exporter)
    llm = _span(exporter, "llm")
    assert llm.attributes["gen_ai.provider.name"] == "xiaomi"
    assert llm.attributes["gen_ai.request.model"] == "mimo-v2.5-pro"
    # rule rows must NOT emit a nested LLM span
    exporter2 = InMemorySpanExporter()
    export_run_to_otel(
        _write_traces(tmp_path / "rule.jsonl", [_rule_row()]), exporter=exporter2
    )
    assert "LLM" not in _kinds(exporter2)


def test_valid_otlp(tmp_path: Path) -> None:
    traces = _write_traces(tmp_path / "traces.jsonl", [_rule_row(), _llm_row()])
    exporter = InMemorySpanExporter()
    export_run_to_otel(traces, exporter=exporter)

    spans = exporter.get_finished_spans()
    assert spans
    for span in spans:
        # Each span serialises to valid OTLP JSON (a valid OpenInference trace is valid OTLP).
        payload = json.loads(span.to_json())
        assert payload["name"]
        assert payload["context"]["trace_id"]


def test_export_default_off(tmp_path: Path) -> None:
    # The exporter only runs when explicitly called; merely having a run on disk emits nothing.
    traces = _write_traces(tmp_path / "traces.jsonl", [_rule_row()])
    exporter = InMemorySpanExporter()
    assert exporter.get_finished_spans() == ()
    # And an empty trace file produces zero spans.
    empty = _write_traces(tmp_path / "empty.jsonl", [])
    assert export_run_to_otel(empty, exporter=exporter) == 0
    assert exporter.get_finished_spans() == ()
    del traces
