"""Q4-P3 detection/routing calibration tests (SPEC_Q4_P2_P3 §2.3).

These lock the Q4-P1 root-cause fixes:
  A. superseded_by survives ingest onto the chunk and is read by GovernanceSignals.
  B. STALE_PROCEDURE triggers on either a deprecated+superseded chunk OR an active SOP
     whose overlay_relation_note.type == "stale_procedure" (no deprecated chunk needed).
  + spurious PERMISSION_BLOCKED is suppressed for authorized actors with sufficient
    evidence, while real unauthorized actors are still blocked.
  + the validator is asserted UNCHANGED (regression lock; validator.py must not move).
"""

from __future__ import annotations

from app.core.enums import DocumentStatus, DocumentType
from app.govern.conditions import (
    ActorContext,
    ConditionReport,
    GovernanceAction,
    GovernanceSignals,
    OpsCondition,
    detect_conditions,
)
from app.govern.context import GovernanceControllerContext
from app.govern.controller import GovernanceRuleController
from app.govern.governor import govern
from app.govern.sinks import LocalJsonlSink
from app.govern.validator import GovernanceBudget, GovernanceProposal, validate_governance
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.ingest.chunker import chunk_parsed_document
from app.schemas.document import DocumentMetadata, ParsedDocument, ParsedSection
from app.schemas.retrieval import RetrievedChunk
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


# --------------------------------------------------------------------------- #
# Detection: root cause A (superseded_by ingest loss)
# --------------------------------------------------------------------------- #
def test_superseded_by_survives_ingest() -> None:
    metadata = DocumentMetadata(
        doc_id="doc-psp",
        title="Pod Security Policy (deprecated)",
        doc_type=DocumentType.deployment_guide,
        status=DocumentStatus.deprecated,
        version="kubernetes-website-release-1.24",
        source_path="deprecated/021-psp.md",
        superseded_by="active/003-pod-security-admission.md",
    )
    parsed = ParsedDocument(
        metadata=metadata,
        sections=[
            ParsedSection(
                section_id="s1",
                title="Overview",
                heading_level=1,
                section_path=["PSP"],
                text="PodSecurityPolicy is removed; migrate to Pod Security Admission.",
                line_start=1,
                line_end=2,
            )
        ],
        raw_text="PodSecurityPolicy is removed; migrate to Pod Security Admission.",
    )

    chunks = chunk_parsed_document(parsed)

    assert chunks, "expected at least one chunk"
    assert chunks[0].superseded_by == "active/003-pod-security-admission.md"


def test_governance_signals_read_superseded_by() -> None:
    result = make_retrieved_chunk(
        "c0", "deprecated", doc_id="doc-psp", status=DocumentStatus.deprecated
    )
    result = _with_signals(result, superseded_by="active/003.md")

    signals = GovernanceSignals.from_result(result)

    assert signals.status == DocumentStatus.deprecated.value
    assert signals.superseded_by == "active/003.md"


def test_stale_from_deprecated_chunk() -> None:
    stale = _with_signals(
        make_retrieved_chunk(
            "stale", "PSP migration", doc_id="doc-psp", status=DocumentStatus.deprecated
        ),
        superseded_by="active/pod-security-admission.md",
    )
    report = detect_conditions(
        _pass_result(reranked=[stale], deprecated=[stale]),
        ActorContext(role="editor"),
    )

    assert OpsCondition.stale_procedure in report.conditions
    assert report.stale_doc_ids == ["doc-psp"]


# --------------------------------------------------------------------------- #
# Detection: root cause B (stale via overlay_relation_note, no deprecated chunk)
# --------------------------------------------------------------------------- #
def test_stale_from_overlay_relation_note() -> None:
    # An active SOP that documents a stale procedure, with NO deprecated chunk
    # retrieved at all (ora-002/003 type). Must still raise STALE_PROCEDURE.
    sop = _with_signals(
        make_retrieved_chunk(
            "sop", "Runbook still reads Endpoints API directly", doc_id="sop-deprecation-checks"
        ),
        overlay_relation_note={
            "type": "stale_procedure",
            "anchor_docs": ["active/012-endpoint-slices.md", "active/013-service.md"],
        },
    )
    report = detect_conditions(
        _pass_result(reranked=[sop], acl_surviving=[sop]),
        ActorContext(role="editor"),
    )

    assert OpsCondition.stale_procedure in report.conditions
    assert report.stale_doc_ids == ["sop-deprecation-checks"]


def test_stale_routes_to_flag_stale() -> None:
    report = ConditionReport(
        conditions=[OpsCondition.stale_procedure],
        authorized_actor=True,
        evidence_decision="sufficient",
        stale_doc_ids=["sop-deprecation-checks"],
    )
    proposal = GovernanceRuleController().select(report, GovernanceControllerContext())

    assert proposal.action == GovernanceAction.flag_stale
    assert proposal.args["stale_doc_ids"] == ["sop-deprecation-checks"]


# --------------------------------------------------------------------------- #
# Routing: spurious vs real PERMISSION_BLOCKED
# --------------------------------------------------------------------------- #
def test_authorized_irrelevant_restricted_no_permission_blocked() -> None:
    surviving = make_retrieved_chunk("ok", "current guidance", doc_id="doc-ok")
    blocked = make_retrieved_chunk("blk", "unrelated restricted doc", doc_id="doc-x")
    report = detect_conditions(
        _pass_result(
            reranked=[surviving, blocked],
            acl_surviving=[surviving],
            acl_blocked=[blocked],
            evidence_sufficient=True,
        ),
        ActorContext(role="editor"),
    )

    assert OpsCondition.permission_blocked not in report.conditions


def test_real_unauthorized_still_blocked(tmp_path) -> None:
    # ora-009/010/011 type: role lacks permission -> escalate, no side effect committed.
    report = detect_conditions(
        _pass_result(),
        ActorContext(role="viewer", requested_action=GovernanceAction.open_remediation_ticket),
    )
    assert report.authorized_actor is False
    assert OpsCondition.permission_blocked in report.conditions

    outcome = govern(
        report,
        _pass_result(),
        ActorContext(role="viewer", requested_action=GovernanceAction.open_remediation_ticket),
        GovernanceRuleController(),
        LocalJsonlSink(tmp_path),
    )
    assert outcome.proposal.action == GovernanceAction.escalate_to_human
    assert outcome.record is not None
    assert outcome.record.approval_state == "escalated"


def test_insufficient_evidence_escalates(tmp_path) -> None:
    # True evidence scarcity (no surviving evidence) -> INSUFFICIENT_EVIDENCE -> escalate.
    report = detect_conditions(
        _pass_result(evidence_sufficient=False),
        ActorContext(role="admin"),
    )
    assert report.conditions == [OpsCondition.insufficient_evidence]

    outcome = govern(
        report,
        _pass_result(evidence_sufficient=False),
        ActorContext(role="admin"),
        GovernanceRuleController(),
        LocalJsonlSink(tmp_path),
    )
    assert outcome.proposal.action == GovernanceAction.escalate_to_human


# --------------------------------------------------------------------------- #
# Invariant: validator behaviour is UNCHANGED (regression lock)
# --------------------------------------------------------------------------- #
def test_validator_unchanged() -> None:
    budget = GovernanceBudget()

    stale_report = ConditionReport(
        conditions=[OpsCondition.stale_procedure],
        authorized_actor=True,
        evidence_decision="sufficient",
        stale_doc_ids=["doc-old"],
    )
    ok = validate_governance(
        GovernanceProposal(action=GovernanceAction.flag_stale), stale_report, budget
    )
    assert ok.ok is True and ok.forced_action is None

    # no_op is never validated as an executable action
    assert (
        validate_governance(
            GovernanceProposal(action=GovernanceAction.no_op), stale_report, budget
        ).reject_reason
        == "no_op_not_validated"
    )

    # insufficient evidence forces escalation for non-escalate actions
    insufficient = ConditionReport(
        conditions=[OpsCondition.stale_procedure],
        authorized_actor=True,
        evidence_decision="insufficient",
        stale_doc_ids=["doc-old"],
    )
    reject_ev = validate_governance(
        GovernanceProposal(action=GovernanceAction.flag_stale), insufficient, budget
    )
    assert reject_ev.ok is False
    assert reject_ev.reject_reason == "insufficient_evidence_requires_escalation"
    assert reject_ev.forced_action == GovernanceAction.escalate_to_human

    # unauthorized actor forces escalation for auto/approval tiers
    unauth = ConditionReport(
        conditions=[OpsCondition.config_violation],
        authorized_actor=False,
        evidence_decision="sufficient",
        violating_doc_ids=["doc-a"],
    )
    reject_auth = validate_governance(
        GovernanceProposal(action=GovernanceAction.open_remediation_ticket), unauth, budget
    )
    assert reject_auth.ok is False
    assert reject_auth.reject_reason == "unauthorized_requires_escalation"

    # action not legal for the detected conditions is rejected
    reject_legal = validate_governance(
        GovernanceProposal(action=GovernanceAction.send_alert), stale_report, budget
    )
    assert reject_legal.ok is False
    assert reject_legal.reject_reason == "action_not_legal_for_conditions"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _pass_result(
    *,
    reranked: list[RetrievedChunk] | None = None,
    acl_surviving: list[RetrievedChunk] | None = None,
    acl_blocked: list[RetrievedChunk] | None = None,
    deprecated: list[RetrievedChunk] | None = None,
    evidence_sufficient: bool = True,
) -> RetrievalPassResult:
    reranked = reranked or []
    return RetrievalPassResult(
        query="test query",
        retrieved_chunks=reranked,
        reranked_chunks=reranked,
        state_decision=StateGateDecision(
            surviving_chunks=[
                item for item in reranked if item.chunk.status == DocumentStatus.active
            ],
            deprecated_chunks=deprecated or [],
        ),
        acl_decision=ACLGateDecision(
            surviving_chunks=acl_surviving or [],
            blocked_chunks=acl_blocked or [],
        ),
        conflict_decision=ConflictDecision(),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=evidence_sufficient,
            reason="sufficient" if evidence_sufficient else "test_insufficient",
            support_count=len(acl_surviving or reranked),
            entity_miss=not evidence_sufficient,
        ),
    )


def _with_signals(result: RetrievedChunk, **signals) -> RetrievedChunk:
    return result.model_copy(update={"chunk": result.chunk.model_copy(update=signals)})
