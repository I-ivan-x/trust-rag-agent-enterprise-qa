"""Q4-P6: export existing governance JSONL traces to OpenInference span kinds.

Maps each governance trace row (one case attempt from a run's ``traces.jsonl``) to a
small OpenTelemetry span tree whose spans carry ``openinference.span.kind`` plus
OpenTelemetry GenAI semantic-convention attributes. Every OpenInference trace is a
valid OTLP trace, so the emitted spans can be sent to any OTLP backend
(Datadog/Honeycomb/Phoenix/...).

This is a pure-read observability layer:
  * it never mutates the trace file or any run artifact,
  * OpenTelemetry is an OPTIONAL dependency (``pip install '.[otel]'``); importing this
    module is cheap and safe -- the SDK is only imported when ``export_run_to_otel`` runs,
  * it is OFF by default; nothing in the eval pipeline calls it unless ``--otel`` is passed.

Span tree per case (SPEC_Q4_P6_P7 §1.2):

    AGENT (case root)                      gen_ai.agent.name/id/version
      ├─ RETRIEVER                         gen_ai.data_source.id, retrieved_chunk_ids
      ├─ RERANKER
      ├─ GUARDRAIL  (acl)                  decision, blocked_chunk_ids
      ├─ GUARDRAIL  (document_state)
      ├─ GUARDRAIL  (evidence)             decision
      ├─ AGENT      (controller)           controller.source
      │    └─ LLM   (only when controller_source == "llm")  gen_ai.provider.name/request.model
      ├─ GUARDRAIL  (validator)            validator.ok / forced_action / reject_reason
      └─ TOOL       (action)               tool.name, risk_tier, approval_state, sink_record_id
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SPAN_KIND = "openinference.span.kind"
DEFAULT_SERVICE_NAME = "trustrag-ops-governor"
DATA_SOURCE_ID = "ops_runbook_corpus"

_OTEL_HINT = (
    "OpenTelemetry is not installed. Install the optional group: pip install '.[otel]' "
    "(or 'uv sync --extra otel'). The exporter is opt-in and never required for eval runs."
)


def _require_otel():
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    except ImportError as exc:  # pragma: no cover - exercised only without the optional dep
        raise RuntimeError(_OTEL_HINT) from exc
    return Resource, TracerProvider, SimpleSpanProcessor


def read_trace_rows(traces_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(traces_path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def export_run_to_otel(
    traces_path: Path,
    *,
    exporter: Any | None = None,
    service_name: str = DEFAULT_SERVICE_NAME,
    commit_sha: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> int:
    """Read ``traces.jsonl`` -> build OpenInference span tree -> emit via ``exporter``.

    ``exporter=None`` uses an OTLP gRPC exporter configured from standard
    ``OTEL_EXPORTER_OTLP_*`` env vars. Tests pass an ``InMemorySpanExporter``. Returns the
    number of spans emitted. Pure read: the trace file is never modified.
    """
    Resource, TracerProvider, SimpleSpanProcessor = _require_otel()

    if exporter is None:  # pragma: no cover - requires a live OTLP backend
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter()

    rows = read_trace_rows(traces_path)
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("trustrag.otel_exporter")

    if llm_provider is None or llm_model is None:
        llm_provider, llm_model = _default_llm_identity(llm_provider, llm_model)

    span_count = 0
    for row in rows:
        span_count += _export_case(
            tracer,
            row,
            service_name=service_name,
            commit_sha=commit_sha,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
    provider.force_flush()
    provider.shutdown()
    return span_count


def _export_case(
    tracer,
    row: dict[str, Any],
    *,
    service_name: str,
    commit_sha: str | None,
    llm_provider: str,
    llm_model: str,
) -> int:
    contract = row.get("result_contract") or {}
    gtrace = row.get("governance_trace") or {}
    system_name = row.get("system_name") or contract.get("system_name") or "unknown"
    controller_source = (
        gtrace.get("controller_source") or contract.get("controller_source") or "rule"
    )
    count = 0

    root_attrs = _attrs(
        {
            SPAN_KIND: "AGENT",
            "gen_ai.agent.name": service_name,
            "gen_ai.agent.id": system_name,
            "gen_ai.agent.version": commit_sha,
            "case_id": row.get("case_id"),
            "split": row.get("split"),
            "run_index": row.get("run_index"),
        }
    )
    with tracer.start_as_current_span("governance.case", attributes=root_attrs):
        count += 1

        retrieved = list(row.get("retrieved_chunk_ids") or [])
        with tracer.start_as_current_span(
            "retrieval",
            attributes=_attrs(
                {
                    SPAN_KIND: "RETRIEVER",
                    "gen_ai.data_source.id": DATA_SOURCE_ID,
                    "retrieval.document_count": len(retrieved),
                    "retrieval.retrieved_chunk_ids": retrieved,
                }
            ),
        ):
            count += 1

        with tracer.start_as_current_span(
            "rerank", attributes=_attrs({SPAN_KIND: "RERANKER"})
        ):
            count += 1

        blocked = list(row.get("blocked_chunk_ids") or [])
        count += _guardrail(
            tracer,
            "guardrail.acl",
            name="acl",
            decision="block" if blocked else "pass",
            extra={"guardrail.blocked_chunk_ids": blocked},
        )
        count += _guardrail(
            tracer, "guardrail.document_state", name="document_state", decision="pass"
        )
        evidence_decision = contract.get("evidence_decision")
        count += _guardrail(
            tracer,
            "guardrail.evidence",
            name="evidence",
            decision="pass" if evidence_decision == "sufficient" else "block",
            extra={"guardrail.evidence_decision": evidence_decision},
        )

        with tracer.start_as_current_span(
            "controller",
            attributes=_attrs(
                {
                    SPAN_KIND: "AGENT",
                    "gen_ai.agent.name": "governance-controller",
                    "controller.source": controller_source,
                }
            ),
        ):
            count += 1
            if controller_source == "llm":
                with tracer.start_as_current_span(
                    "llm",
                    attributes=_attrs(
                        {
                            SPAN_KIND: "LLM",
                            "gen_ai.provider.name": llm_provider,
                            "gen_ai.request.model": llm_model,
                            "gen_ai.operation.name": "chat",
                        }
                    ),
                ):
                    count += 1

        count += _guardrail(
            tracer,
            "guardrail.validator",
            name="validator",
            decision="pass" if contract.get("validator_ok", True) else "block",
            extra={
                "validator.ok": contract.get("validator_ok"),
                "validator.forced_action": contract.get("forced_action"),
                "validator.reject_reason": gtrace.get("validator_reject_reason"),
            },
        )

        proposed = gtrace.get("proposed_action") or contract.get("proposed_action")
        with tracer.start_as_current_span(
            "action",
            attributes=_attrs(
                {
                    SPAN_KIND: "TOOL",
                    "tool.name": proposed,
                    "action.risk_tier": gtrace.get("risk_tier") or contract.get("risk_tier"),
                    "action.approval_state": row.get("approval_state")
                    or contract.get("approval_state"),
                    "action.sink_record_id": row.get("sink_record_id"),
                }
            ),
        ):
            count += 1

    return count


def _guardrail(
    tracer, span_name: str, *, name: str, decision: str, extra: dict | None = None
) -> int:
    attrs = {SPAN_KIND: "GUARDRAIL", "guardrail.name": name, "guardrail.decision": decision}
    if extra:
        attrs.update(extra)
    with tracer.start_as_current_span(span_name, attributes=_attrs(attrs)):
        return 1


def _default_llm_identity(provider: str | None, model: str | None) -> tuple[str, str]:
    try:
        from app.core.config import get_settings

        settings = get_settings()
        return provider or settings.llm_provider, model or settings.llm_model_name
    except Exception:  # pragma: no cover - settings always load in this project
        return provider or "unknown", model or "unknown"


def _attrs(values: dict[str, Any]) -> dict[str, Any]:
    """Drop None values (OTLP rejects them) and coerce sequences to tuples of str."""
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            cleaned[key] = [str(item) for item in value]
        elif isinstance(value, bool | int | float | str):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned


def iter_run_traces(run_dir: Path) -> Iterator[dict[str, Any]]:
    yield from read_trace_rows(Path(run_dir) / "traces.jsonl")
