from __future__ import annotations

from app.govern.sinks import ActionRecord, ActionSink


def list_pending(sink: ActionSink) -> list[ActionRecord]:
    records = _list_records(sink)
    return [record for record in records if record.approval_state == "pending_approval"]


def approve_pending(record_id: str, sink: ActionSink) -> ActionRecord:
    return _update_approval_state(record_id, sink, "committed")


def reject_pending(record_id: str, sink: ActionSink) -> ActionRecord:
    return _update_approval_state(record_id, sink, "dropped")


def _list_records(sink: ActionSink) -> list[ActionRecord]:
    list_records = getattr(sink, "list_records", None)
    if not callable(list_records):
        raise TypeError("sink does not support listing action records")
    return list_records()


def _update_approval_state(
    record_id: str,
    sink: ActionSink,
    approval_state: str,
) -> ActionRecord:
    update = getattr(sink, "update_approval_state", None)
    if not callable(update):
        raise TypeError("sink does not support approval state updates")
    return update(record_id, approval_state)
