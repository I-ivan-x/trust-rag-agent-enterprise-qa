from __future__ import annotations

from app.context.context_assembler import assemble_context
from app.core.enums import AccessLevel
from app.guards.acl_gate import apply_acl_gate
from tests.helpers import make_retrieved_chunk


def test_acl_allows_public_chunks() -> None:
    chunk = make_retrieved_chunk(
        "chunk-public",
        "Public handbook.",
        access_level=AccessLevel.public,
    )

    decision = apply_acl_gate([chunk], user_role="guest", user_clearance="public")

    assert decision.surviving_chunks == [chunk]
    assert decision.blocked_chunks == []


def test_acl_internal_requires_internal_clearance() -> None:
    chunk = make_retrieved_chunk(
        "chunk-internal",
        "Internal API.",
        access_level=AccessLevel.internal,
    )

    denied = apply_acl_gate([chunk], user_role="employee", user_clearance="public")
    allowed = apply_acl_gate([chunk], user_role="employee", user_clearance="internal")

    assert denied.surviving_chunks == []
    assert denied.blocked_chunks == [chunk]
    assert allowed.surviving_chunks == [chunk]


def test_acl_restricted_requires_allowed_role() -> None:
    chunk = make_retrieved_chunk(
        "chunk-restricted",
        "Admin keys must be rotated.",
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
    )

    denied = apply_acl_gate([chunk], user_role="employee", user_clearance="internal")
    allowed = apply_acl_gate([chunk], user_role="security_admin", user_clearance="internal")

    assert denied.blocked_chunks == [chunk]
    assert allowed.surviving_chunks == [chunk]


def test_employee_cannot_see_security_admin_restricted_chunk() -> None:
    chunk = make_retrieved_chunk(
        "doc-security-admin-key-rotation-sop::chunk-0000",
        "Admin keys must be rotated every 90 days.",
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
    )

    decision = apply_acl_gate([chunk], user_role="employee", user_clearance="internal")

    assert decision.surviving_chunks == []
    assert (
        decision.blocked_chunks[0].chunk.chunk_id
        == "doc-security-admin-key-rotation-sop::chunk-0000"
    )


def test_blocked_chunks_do_not_enter_answer_context() -> None:
    allowed = make_retrieved_chunk("chunk-allowed", "Allowed evidence.")
    blocked = make_retrieved_chunk(
        "chunk-blocked",
        "Restricted evidence.",
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
    )

    decision = apply_acl_gate(
        [allowed, blocked],
        user_role="employee",
        user_clearance="internal",
    )
    context = assemble_context("query", decision.surviving_chunks)

    assert [chunk.chunk_id for chunk in context.chunks] == ["chunk-allowed"]
