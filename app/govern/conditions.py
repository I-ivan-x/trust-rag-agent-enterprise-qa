from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.diagnosis import _conflict_group_ids
from app.core.enums import DocumentStatus
from app.schemas.retrieval import RetrievedChunk
from app.workflow.state import RetrievalPassResult


class OpsCondition(StrEnum):
    stale_procedure = "STALE_PROCEDURE"
    config_violation = "CONFIG_VIOLATION"
    active_active_conflict = "ACTIVE_ACTIVE_CONFLICT"
    missing_prereq = "MISSING_PREREQ"
    broken_xref = "BROKEN_XREF"
    policy_violation = "POLICY_VIOLATION"
    insufficient_evidence = "INSUFFICIENT_EVIDENCE"
    permission_blocked = "PERMISSION_BLOCKED"


class GovernanceAction(StrEnum):
    flag_stale = "flag_stale"
    open_remediation_ticket = "open_remediation_ticket"
    send_alert = "send_alert"
    escalate_to_human = "escalate_to_human"
    no_op = "no_op"


class RiskTier(StrEnum):
    auto = "auto"
    approval = "approval"
    terminal = "terminal"


RISK_TIER: dict[GovernanceAction, RiskTier] = {
    GovernanceAction.flag_stale: RiskTier.auto,
    GovernanceAction.open_remediation_ticket: RiskTier.approval,
    GovernanceAction.send_alert: RiskTier.approval,
    GovernanceAction.escalate_to_human: RiskTier.terminal,
}

DEFAULT_AUTHORIZED_ROLES: dict[GovernanceAction, frozenset[str]] = {
    GovernanceAction.flag_stale: frozenset({"admin", "editor"}),
    GovernanceAction.open_remediation_ticket: frozenset({"admin", "editor"}),
    GovernanceAction.send_alert: frozenset({"admin"}),
    GovernanceAction.escalate_to_human: frozenset({"admin", "editor", "viewer"}),
}


class ConditionReport(BaseModel):
    conditions: list[OpsCondition] = Field(default_factory=list)
    authorized_actor: bool
    evidence_decision: Literal["sufficient", "insufficient"]
    stale_doc_ids: list[str] = Field(default_factory=list)
    violating_doc_ids: list[str] = Field(default_factory=list)
    conflict_group_ids: list[str] = Field(default_factory=list)
    broken_xref_doc_ids: list[str] = Field(default_factory=list)
    permission_blocked_count: int = Field(ge=0, default=0)


@dataclass(frozen=True)
class ActorContext:
    role: str
    clearance: str | None = "internal"
    department: str | None = None
    requested_action: GovernanceAction | None = None


@dataclass(frozen=True)
class GovernanceSignals:
    doc_id: str
    status: str
    superseded_by: str | None
    overlay_relation_note: Any
    policy_ref: str | None
    metadata_origin: str | None

    @classmethod
    def from_result(cls, result: RetrievedChunk) -> GovernanceSignals:
        chunk = result.chunk
        return cls(
            doc_id=chunk.doc_id,
            status=_value(_read_signal(chunk, "status")) or "",
            superseded_by=_string_or_none(_read_signal(chunk, "superseded_by")),
            overlay_relation_note=_read_signal(chunk, "overlay_relation_note"),
            policy_ref=_string_or_none(_read_signal(chunk, "policy_ref")),
            metadata_origin=_string_or_none(_read_signal(chunk, "metadata_origin")),
        )


def detect_conditions(
    pass_result: RetrievalPassResult,
    actor: ActorContext,
    *,
    authorized_roles: Mapping[
        GovernanceAction,
        frozenset[str],
    ] = DEFAULT_AUTHORIZED_ROLES,
) -> ConditionReport:
    conditions: list[OpsCondition] = []
    evidence_decision: Literal["sufficient", "insufficient"] = (
        "sufficient" if pass_result.evidence_decision.evidence_sufficient else "insufficient"
    )
    requested_action = actor.requested_action
    authorized_actor = _is_authorized(actor.role, requested_action, authorized_roles)
    permission_blocked_count = len(pass_result.acl_decision.blocked_chunks)
    if not authorized_actor:
        # Real authorization failure: the actor's role lacks permission for the action.
        permission_blocked_count += 1
        _add_condition(conditions, OpsCondition.permission_blocked)
    elif pass_result.acl_decision.blocked_chunks and evidence_decision == "insufficient":
        # ACL filtering only counts as PERMISSION_BLOCKED when it actually starved the
        # answer of evidence. An authorized actor whose evidence is sufficient and who
        # merely had irrelevant restricted neighbors filtered out is NOT permission
        # blocked -- recording it here spuriously short-circuited stale/config/xref to
        # escalate (Q4-P1 over-escalation root cause).
        _add_condition(conditions, OpsCondition.permission_blocked)

    conflict_group_ids = _conflict_group_ids(pass_result)
    if conflict_group_ids:
        _add_condition(conditions, OpsCondition.active_active_conflict)

    stale_doc_ids = _stale_doc_ids(pass_result)
    if stale_doc_ids:
        _add_condition(conditions, OpsCondition.stale_procedure)

    relation_conditions, broken_xref_doc_ids = _relation_conditions(pass_result)
    for condition in relation_conditions:
        _add_condition(conditions, condition)

    policy_conditions, violating_doc_ids = _policy_conditions(pass_result)
    for condition in policy_conditions:
        _add_condition(conditions, condition)

    if evidence_decision == "insufficient" and not conditions:
        _add_condition(conditions, OpsCondition.insufficient_evidence)

    return ConditionReport(
        conditions=conditions,
        authorized_actor=authorized_actor,
        evidence_decision=evidence_decision,
        stale_doc_ids=stale_doc_ids,
        violating_doc_ids=violating_doc_ids,
        conflict_group_ids=conflict_group_ids,
        broken_xref_doc_ids=broken_xref_doc_ids,
        permission_blocked_count=permission_blocked_count,
    )


def _is_authorized(
    role: str,
    requested_action: GovernanceAction | None,
    authorized_roles: Mapping[GovernanceAction, frozenset[str]],
) -> bool:
    if requested_action is None:
        return True
    return role.strip().lower() in authorized_roles.get(requested_action, frozenset())


def _stale_doc_ids(pass_result: RetrievalPassResult) -> list[str]:
    doc_ids: set[str] = set()
    for signal in _signals(pass_result):
        # (a) a retrieved deprecated doc that points at its replacement, or
        if signal.status == DocumentStatus.deprecated.value and signal.superseded_by:
            doc_ids.add(signal.doc_id)
            continue
        # (b) an active SOP whose overlay relation flags it as a stale procedure
        #     (cross-references a deprecated/superseded target). The deprecated doc
        #     itself need not be retrieved -- the active SOP is enough to trigger.
        relation = _relation_mapping(signal.overlay_relation_note)
        if _value(relation.get("type")) == OpsCondition.stale_procedure.value.lower():
            doc_ids.add(signal.doc_id)
    return sorted(doc_ids)


def _relation_conditions(
    pass_result: RetrievalPassResult,
) -> tuple[list[OpsCondition], list[str]]:
    conditions: list[OpsCondition] = []
    broken_doc_ids: set[str] = set()
    for signal in _signals(pass_result):
        relation = _relation_mapping(signal.overlay_relation_note)
        relation_type = _value(relation.get("type"))
        target_status = _value(relation.get("target_status"))
        target_doc_id = _string_or_none(relation.get("target_doc_id")) or signal.doc_id
        if target_status not in {"deprecated", "missing"}:
            continue
        broken_doc_ids.add(target_doc_id)
        if relation_type in {"prereq", "missing_prereq", "prerequisite"}:
            _add_condition(conditions, OpsCondition.missing_prereq)
            continue
        _add_condition(conditions, OpsCondition.broken_xref)
    return conditions, sorted(broken_doc_ids)


def _policy_conditions(
    pass_result: RetrievalPassResult,
) -> tuple[list[OpsCondition], list[str]]:
    policy_doc_ids = {
        signal.doc_id for signal in _signals(pass_result) if signal.doc_id.startswith("policy-")
    }
    conditions: list[OpsCondition] = []
    violating_doc_ids: set[str] = set()
    for signal in _signals(pass_result):
        if not signal.policy_ref:
            continue
        relation = _relation_mapping(signal.overlay_relation_note)
        relation_type = _value(relation.get("type"))
        has_policy_doc = signal.policy_ref in policy_doc_ids
        if relation_type in {"violates_policy", "config_violation"} or has_policy_doc:
            violating_doc_ids.add(signal.doc_id)
            _add_condition(conditions, OpsCondition.config_violation)
        if relation_type == "policy_violation":
            violating_doc_ids.add(signal.doc_id)
            _add_condition(conditions, OpsCondition.policy_violation)
    return conditions, sorted(violating_doc_ids)


def _signals(pass_result: RetrievalPassResult) -> list[GovernanceSignals]:
    by_chunk_id: dict[str, RetrievedChunk] = {}
    for result in [
        *pass_result.reranked_chunks,
        *pass_result.state_decision.deprecated_chunks,
        *pass_result.acl_decision.surviving_chunks,
        *pass_result.acl_decision.blocked_chunks,
    ]:
        by_chunk_id[result.chunk.chunk_id] = result
    return [GovernanceSignals.from_result(result) for result in by_chunk_id.values()]


def _read_signal(obj: Any, field_name: str) -> Any:
    if hasattr(obj, field_name):
        return getattr(obj, field_name)
    metadata = getattr(obj, "metadata", None)
    if isinstance(metadata, Mapping):
        return metadata.get(field_name)
    return None


def _relation_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return {}
    lowered = value.lower()
    if "missing" in lowered:
        return {"type": "xref", "target_status": "missing"}
    if "deprecated" in lowered:
        return {"type": "xref", "target_status": "deprecated"}
    if "violates_policy" in lowered or "config_violation" in lowered:
        return {"type": "violates_policy"}
    if "policy_violation" in lowered:
        return {"type": "policy_violation"}
    return {}


def _value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, StrEnum):
        return value.value
    return str(value).strip().lower() or None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _add_condition(conditions: list[OpsCondition], condition: OpsCondition) -> None:
    if condition not in conditions:
        conditions.append(condition)
