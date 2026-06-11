from __future__ import annotations

from app.core.enums import DocumentStatus
from app.guards.conflict_detector import detect_minimal_conflict
from app.guards.document_state_gate import apply_document_state_gate
from tests.helpers import make_retrieved_chunk


def test_active_chunks_survive_state_gate() -> None:
    chunk = make_retrieved_chunk("chunk-active", "Active text.", status=DocumentStatus.active)

    decision = apply_document_state_gate([chunk])

    assert decision.surviving_chunks == [chunk]
    assert decision.deprecated_chunks == []
    assert decision.blocked_chunks == []


def test_deprecated_chunks_enter_warning_path() -> None:
    chunk = make_retrieved_chunk(
        "chunk-deprecated",
        "Deprecated text.",
        status=DocumentStatus.deprecated,
    )

    decision = apply_document_state_gate([chunk])

    assert decision.surviving_chunks == []
    assert decision.deprecated_chunks == [chunk]
    assert "Deprecated evidence" in decision.warnings[0]


def test_archived_and_draft_chunks_are_blocked() -> None:
    archived = make_retrieved_chunk("chunk-archived", "Archived.", status=DocumentStatus.archived)
    draft = make_retrieved_chunk("chunk-draft", "Draft.", status=DocumentStatus.draft)

    decision = apply_document_state_gate([archived, draft])

    assert decision.surviving_chunks == []
    assert decision.blocked_chunks == [archived, draft]


def test_active_vs_deprecated_same_conflict_group_does_not_trigger_conflict() -> None:
    active = make_retrieved_chunk(
        "chunk-active",
        "Active.",
        doc_id="doc-current",
        status=DocumentStatus.active,
        conflict_group_id="token-lifetime",
    )
    deprecated = make_retrieved_chunk(
        "chunk-deprecated",
        "Deprecated.",
        doc_id="doc-old",
        status=DocumentStatus.deprecated,
        conflict_group_id="token-lifetime",
    )

    state = apply_document_state_gate([active, deprecated])
    conflict = detect_minimal_conflict(state.surviving_chunks)

    assert conflict.has_conflict is False
