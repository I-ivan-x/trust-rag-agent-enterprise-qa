from __future__ import annotations

from types import SimpleNamespace

from app.core.enums import AccessLevel, DocumentStatus
from app.guards.acl_gate import ACLGateDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.service.chat_service import (
    _acl_denies_required_evidence,
    _deprecated_warning_for_policy,
)
from tests.helpers import make_retrieved_chunk


def test_legacy_policy_blocks_matching_restricted_neighbor() -> None:
    clean = make_retrieved_chunk("chunk-clean", "Admin key rotation is tracked elsewhere.")
    restricted = make_retrieved_chunk(
        "chunk-restricted",
        "Admin keys must be rotated every 90 days.",
        access_level=AccessLevel.restricted,
    )
    pass_result = _pass_result(
        query="How often must admin keys be rotated?",
        surviving=[clean],
        blocked=[restricted],
        evidence_sufficient=True,
    )

    assert _acl_denies_required_evidence(pass_result, trust_gate_policy="legacy") is True


def test_neighbor_tolerant_policy_blocks_query_matching_restricted_evidence() -> None:
    clean = make_retrieved_chunk("chunk-clean", "Admin key rotation is documented publicly.")
    restricted = make_retrieved_chunk(
        "chunk-restricted",
        "Admin keys must be rotated every 90 days.",
        access_level=AccessLevel.restricted,
    )
    pass_result = _pass_result(
        query="How often must admin keys be rotated?",
        surviving=[clean],
        blocked=[restricted],
        evidence_sufficient=True,
    )

    assert (
        _acl_denies_required_evidence(
            pass_result,
            trust_gate_policy="neighbor_tolerant",
        )
        is True
    )


def test_neighbor_tolerant_policy_ignores_unrelated_restricted_neighbor() -> None:
    clean = make_retrieved_chunk("chunk-clean", "Public CORS setup uses middleware.")
    restricted = make_retrieved_chunk(
        "chunk-restricted",
        "Admin keys must be rotated every 90 days.",
        access_level=AccessLevel.restricted,
    )
    pass_result = _pass_result(
        query="How do I configure CORS?",
        surviving=[clean],
        blocked=[restricted],
        evidence_sufficient=True,
    )

    assert (
        _acl_denies_required_evidence(
            pass_result,
            trust_gate_policy="neighbor_tolerant",
        )
        is False
    )


def test_neighbor_tolerant_policy_still_blocks_when_only_restricted_evidence_remains() -> None:
    restricted = make_retrieved_chunk(
        "chunk-restricted",
        "Admin keys must be rotated every 90 days.",
        access_level=AccessLevel.restricted,
    )
    pass_result = _pass_result(
        query="How often must admin keys be rotated?",
        surviving=[],
        blocked=[restricted],
        evidence_sufficient=False,
    )

    assert (
        _acl_denies_required_evidence(
            pass_result,
            trust_gate_policy="neighbor_tolerant",
        )
        is True
    )


def test_legacy_policy_warns_on_deprecated_neighbor_even_with_clean_evidence() -> None:
    active = make_retrieved_chunk(
        "chunk-active",
        "In v1 compatibility mode, the token lifetime is documented in the active guide.",
    )
    deprecated = make_retrieved_chunk(
        "chunk-deprecated",
        "In v1 the access token lifetime was 60 minutes.",
        status=DocumentStatus.deprecated,
    )
    pass_result = _pass_result(
        query="What was the v1 access token lifetime?",
        surviving=[active],
        deprecated=[deprecated],
        evidence_sufficient=True,
    )

    assert _deprecated_warning_for_policy(pass_result, trust_gate_policy="legacy") is True


def test_neighbor_tolerant_policy_suppresses_deprecated_neighbor_with_clean_evidence() -> None:
    active = make_retrieved_chunk(
        "chunk-active",
        "In v1 compatibility mode, the token lifetime is documented in the active guide.",
    )
    deprecated = make_retrieved_chunk(
        "chunk-deprecated",
        "In v1 the access token lifetime was 60 minutes.",
        status=DocumentStatus.deprecated,
    )
    pass_result = _pass_result(
        query="What was the v1 access token lifetime?",
        surviving=[active],
        deprecated=[deprecated],
        evidence_sufficient=True,
    )

    assert (
        _deprecated_warning_for_policy(
            pass_result,
            trust_gate_policy="neighbor_tolerant",
        )
        is False
    )


def test_neighbor_tolerant_policy_warns_when_clean_evidence_is_insufficient() -> None:
    deprecated = make_retrieved_chunk(
        "chunk-deprecated",
        "In v1 the access token lifetime was 60 minutes.",
        status=DocumentStatus.deprecated,
    )
    pass_result = _pass_result(
        query="What was the v1 access token lifetime?",
        surviving=[],
        deprecated=[deprecated],
        evidence_sufficient=False,
    )

    assert (
        _deprecated_warning_for_policy(
            pass_result,
            trust_gate_policy="neighbor_tolerant",
        )
        is True
    )


def _pass_result(
    *,
    query: str,
    surviving=None,
    blocked=None,
    deprecated=None,
    evidence_sufficient: bool,
):
    return SimpleNamespace(
        query=query,
        acl_decision=ACLGateDecision(
            surviving_chunks=surviving or [],
            blocked_chunks=blocked or [],
        ),
        state_decision=StateGateDecision(
            surviving_chunks=surviving or [],
            deprecated_chunks=deprecated or [],
        ),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=evidence_sufficient,
            reason="sufficient" if evidence_sufficient else "no_surviving_chunks",
            support_count=len(surviving or []),
        ),
    )
