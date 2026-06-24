from __future__ import annotations

from pathlib import Path

from app.govern.conditions import OpsCondition
from app.govern.sinks import ACTION_STORE_DIR, ActionRecord, LocalJsonlSink

try:  # pragma: no cover - optional demo dependency
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # pragma: no cover - covered by optional dependency install
    FastMCP = None  # type: ignore[assignment]


class RunbookOpsMCPTools:
    def __init__(self, sink: LocalJsonlSink | None = None) -> None:
        self.sink = sink or LocalJsonlSink()

    def create_ticket(
        self,
        condition: str,
        doc_ids: list[str],
        citations: list[str],
        actor: str,
    ) -> dict:
        record = self.sink.create_ticket(
            condition=OpsCondition(condition),
            doc_ids=doc_ids,
            evidence_citations=citations,
            actor_role=actor,
        )
        return _record_payload(record)

    def send_alert(
        self,
        condition: str,
        conflict_doc_ids: list[str],
        citations: list[str],
        actor: str,
    ) -> dict:
        record = self.sink.send_alert(
            condition=OpsCondition(condition),
            doc_ids=conflict_doc_ids,
            evidence_citations=citations,
            actor_role=actor,
        )
        return _record_payload(record)

    def flag_document(
        self,
        doc_id: str,
        reason: str,
        citations: list[str],
        actor: str = "system",
    ) -> dict:
        record = self.sink.flag_document(
            condition=OpsCondition.stale_procedure,
            doc_ids=[doc_id],
            evidence_citations=citations,
            actor_role=actor,
        )
        payload = _record_payload(record)
        payload["reason"] = reason
        return payload

    def escalate(
        self,
        reason: str,
        context: dict,
        actor: str = "system",
    ) -> dict:
        doc_ids = [str(doc_id) for doc_id in context.get("doc_ids", [])]
        citations = [str(chunk_id) for chunk_id in context.get("citations", [])]
        condition_value = context.get("condition")
        condition = OpsCondition(condition_value) if condition_value else None
        record = self.sink.escalate(
            condition=condition,
            doc_ids=doc_ids,
            evidence_citations=citations,
            actor_role=actor,
        )
        payload = _record_payload(record)
        payload["reason"] = reason
        return payload


def create_mcp_server(sink_root: Path | None = None):
    if FastMCP is None:
        raise RuntimeError("Install the optional 'mcp' dependency to run the MCP server.")
    tools = RunbookOpsMCPTools(LocalJsonlSink(sink_root or ACTION_STORE_DIR))
    server = FastMCP("runbook_ops_mcp")

    @server.tool()
    def create_ticket(
        condition: str,
        doc_ids: list[str],
        citations: list[str],
        actor: str,
    ) -> dict:
        return tools.create_ticket(condition, doc_ids, citations, actor)

    @server.tool()
    def send_alert(
        condition: str,
        conflict_doc_ids: list[str],
        citations: list[str],
        actor: str,
    ) -> dict:
        return tools.send_alert(condition, conflict_doc_ids, citations, actor)

    @server.tool()
    def flag_document(
        doc_id: str,
        reason: str,
        citations: list[str],
        actor: str = "system",
    ) -> dict:
        return tools.flag_document(doc_id, reason, citations, actor)

    @server.tool()
    def escalate(reason: str, context: dict, actor: str = "system") -> dict:
        return tools.escalate(reason, context, actor)

    return server


def main() -> None:  # pragma: no cover - demo entrypoint
    create_mcp_server().run()


def _record_payload(record: ActionRecord) -> dict:
    return record.model_dump(mode="json")


if __name__ == "__main__":  # pragma: no cover - demo entrypoint
    main()
