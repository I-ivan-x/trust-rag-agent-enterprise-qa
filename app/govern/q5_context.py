"""Q5 authorized decision context and per-proposal authorization.

This module is intentionally parallel to the frozen Q4 governance context. It
never changes Q4 controller or validator behavior, and it never copies text from
ACL-blocked chunks into runtime context, prompts, or traces.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.govern.conditions import (
    DEFAULT_AUTHORIZED_ROLES,
    GovernanceAction,
    OpsCondition,
)
from app.schemas.q5_task import (
    Q5_GOLD_ONLY_FIELDS,
    Q5ActorClaims,
    Q5ObservationTool,
    RequestedCapability,
)
from app.schemas.retrieval import RetrievedChunk
from app.workflow.state import RetrievalPassResult

Q5_EXCERPT_CHAR_LIMIT = 600
Q5_AUTHORIZED_TEXT_CHAR_LIMIT = 4_000
Q5_RELATION_SUMMARY_CHAR_LIMIT = 400


class Q5AuthorizedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    text_excerpt: str = Field(max_length=Q5_EXCERPT_CHAR_LIMIT)
    status: str = Field(min_length=1)
    section_path: list[str] = Field(default_factory=list)
    source_origin: str = Field(min_length=1)
    corpus_source: str = Field(min_length=1)
    retrieval_source: str = Field(min_length=1)
    rerank_score: float | None = None
    relation_summary: str | None = Field(
        default=None,
        max_length=Q5_RELATION_SUMMARY_CHAR_LIMIT,
    )


class Q5BlockedEvidenceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opaque_chunk_id: str = Field(min_length=1)
    block_reason: Literal["acl_denied"] = "acl_denied"


class Q5TrustedObservation(BaseModel):
    """Sanitized observation slice allowed to enter the decision context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: Q5ObservationTool
    request_id: str = Field(min_length=1)
    status: Literal["ok", "not_found", "timeout", "invalid"]
    observation: dict[str, Any] | None = None
    provenance: str = Field(min_length=1)

    @model_validator(mode="after")
    def _reject_forbidden_nested_fields(self) -> Q5TrustedObservation:
        assert_q5_no_gold_or_control_fields(self.observation)
        return self


class Q5DecisionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1)
    actor_claims: Q5ActorClaims
    requested_capability: RequestedCapability
    resource_refs: list[str] = Field(default_factory=list)
    available_tools: list[Q5ObservationTool] = Field(default_factory=list)
    conditions: list[OpsCondition] = Field(default_factory=list)
    evidence_decision: Literal["sufficient", "insufficient"]
    authorized_evidence: list[Q5AuthorizedEvidence] = Field(default_factory=list)
    blocked_evidence_metadata: list[Q5BlockedEvidenceMetadata] = Field(
        default_factory=list
    )
    observations: list[Q5TrustedObservation] = Field(default_factory=list)
    legal_terminal_actions: list[GovernanceAction] = Field(default_factory=list)
    remaining_observation_budget: int = Field(ge=0, le=2)
    remaining_terminal_budget: int = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _validate_context_budgets_and_ids(self) -> Q5DecisionContext:
        total_text = sum(len(item.text_excerpt) for item in self.authorized_evidence)
        if total_text > Q5_AUTHORIZED_TEXT_CHAR_LIMIT:
            raise ValueError("authorized evidence text exceeds the 4000-char budget")
        _require_unique(
            (item.chunk_id for item in self.authorized_evidence),
            field="authorized evidence chunk_id",
        )
        _require_unique(
            (item.opaque_chunk_id for item in self.blocked_evidence_metadata),
            field="blocked evidence opaque_chunk_id",
        )
        _require_unique(self.resource_refs, field="resource_refs")
        _require_unique(self.available_tools, field="available_tools")
        _require_unique(self.legal_terminal_actions, field="legal_terminal_actions")
        assert_q5_no_gold_or_control_fields(self.model_dump(mode="json"))
        return self


class Q5ProposalKind(StrEnum):
    observe = "observe"
    terminal = "terminal"


class Q5StructuredProposal(BaseModel):
    """Strict LLM output contract; risk and authorization remain code-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Q5ProposalKind
    tool: Q5ObservationTool | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    action: GovernanceAction | None = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    reason_summary: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def _validate_proposal_shape(self) -> Q5StructuredProposal:
        if self.kind is Q5ProposalKind.observe:
            if self.tool is None or self.action is not None:
                raise ValueError("observe proposal requires tool and forbids action")
        elif self.tool is not None or self.action is None:
            raise ValueError("terminal proposal requires action and forbids tool")

        if "\n" in self.reason_summary or "\r" in self.reason_summary:
            raise ValueError("reason_summary must be one line")
        _require_unique(self.evidence_chunk_ids, field="evidence_chunk_ids")
        assert_q5_no_gold_or_control_fields(self.args)
        return self


class Q5AuthorizationVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    reason_code: Literal[
        "allowed",
        "capability_action_denied",
        "role_action_denied",
        "tool_not_available",
        "observation_role_denied",
    ]
    actor_role: str
    requested_capability: RequestedCapability
    proposal_kind: Q5ProposalKind
    action: GovernanceAction | None = None
    tool: Q5ObservationTool | None = None


_SAFE_TERMINAL_ACTIONS = frozenset(
    {GovernanceAction.no_op, GovernanceAction.escalate_to_human}
)
Q5_CAPABILITY_TO_ACTIONS: Mapping[
    RequestedCapability,
    frozenset[GovernanceAction],
] = MappingProxyType({
    RequestedCapability.document_maintenance: frozenset(
        {GovernanceAction.flag_stale}
    ),
    RequestedCapability.remediation_management: frozenset(
        {GovernanceAction.open_remediation_ticket}
    ),
    RequestedCapability.incident_response: frozenset(
        {GovernanceAction.send_alert}
    ),
    RequestedCapability.investigate: _SAFE_TERMINAL_ACTIONS,
})
_OBSERVATION_ROLES = frozenset().union(*DEFAULT_AUTHORIZED_ROLES.values())
_CONTROL_ONLY_FIELDS = frozenset(
    {
        "auth",
        "authorization",
        "authorized_actor",
        "actor_authorized",
        "risk",
        "risk_tier",
    }
)


def build_q5_decision_context(
    pass_result: RetrievalPassResult,
    *,
    actor_claims: Q5ActorClaims,
    requested_capability: RequestedCapability,
    conditions: Sequence[OpsCondition],
    evidence_decision: Literal["sufficient", "insufficient"],
    condition_legal_actions: Sequence[GovernanceAction],
    resource_refs: Sequence[str] = (),
    available_tools: Sequence[Q5ObservationTool] = (),
    observations: Sequence[Q5TrustedObservation] = (),
    remaining_observation_budget: int = 2,
    remaining_terminal_budget: int = 1,
) -> Q5DecisionContext:
    """Build a Q5 context using ACL-surviving evidence as the only text source."""

    _assert_acl_partition_disjoint(
        pass_result.acl_decision.surviving_chunks,
        pass_result.acl_decision.blocked_chunks,
    )
    authorized_evidence = _authorized_evidence(
        pass_result.acl_decision.surviving_chunks
    )
    blocked_metadata = _blocked_metadata(pass_result.acl_decision.blocked_chunks)
    legal_actions = legal_q5_terminal_actions(
        actor_claims,
        requested_capability,
        candidates=condition_legal_actions,
    )
    context = Q5DecisionContext(
        query=pass_result.query,
        actor_claims=actor_claims,
        requested_capability=requested_capability,
        resource_refs=list(resource_refs),
        available_tools=list(available_tools),
        conditions=list(conditions),
        evidence_decision=evidence_decision,
        authorized_evidence=authorized_evidence,
        blocked_evidence_metadata=blocked_metadata,
        observations=list(observations),
        legal_terminal_actions=legal_actions,
        remaining_observation_budget=remaining_observation_budget,
        remaining_terminal_budget=remaining_terminal_budget,
    )
    assert_q5_no_gold_or_control_fields(q5_prompt_payload(context))
    return context


def q5_prompt_payload(context: Q5DecisionContext) -> dict[str, Any]:
    """Return only explicitly reviewed fields; never dump the whole context blindly."""

    assert_q5_no_gold_or_control_fields(context.model_dump(mode="json"))
    payload = {
        "query": context.query,
        "actor_claims": {
            "role": context.actor_claims.role,
            "clearance": context.actor_claims.clearance,
            "department": context.actor_claims.department,
        },
        "requested_capability": context.requested_capability.value,
        "resource_refs": list(context.resource_refs),
        "available_tools": [tool.value for tool in context.available_tools],
        "conditions": [condition.value for condition in context.conditions],
        "evidence_decision": context.evidence_decision,
        "authorized_evidence": [
            {
                "chunk_id": item.chunk_id,
                "doc_id": item.doc_id,
                "text_excerpt": item.text_excerpt,
                "status": item.status,
                "section_path": item.section_path,
                "source_origin": item.source_origin,
                "corpus_source": item.corpus_source,
                "retrieval_source": item.retrieval_source,
                "rerank_score": item.rerank_score,
                "relation_summary": item.relation_summary,
            }
            for item in context.authorized_evidence
        ],
        "blocked_evidence": {
            "blocked_count": len(context.blocked_evidence_metadata),
            "items": [
                {
                    "opaque_chunk_id": item.opaque_chunk_id,
                    "block_reason": item.block_reason,
                }
                for item in context.blocked_evidence_metadata
            ],
        },
        "observations": [
            {
                "tool_name": item.tool_name.value,
                "request_id": item.request_id,
                "status": item.status,
                "observation": item.observation,
                "provenance": item.provenance,
            }
            for item in context.observations
        ],
        "legal_terminal_actions": [
            action.value for action in context.legal_terminal_actions
        ],
        "remaining_observation_budget": context.remaining_observation_budget,
        "remaining_terminal_budget": context.remaining_terminal_budget,
    }
    assert_q5_no_gold_or_control_fields(payload)
    return payload


def build_q5_prompt(context: Q5DecisionContext) -> str:
    assert_q5_no_gold_or_control_fields(context.model_dump(mode="json"))
    payload = q5_prompt_payload(context)
    assert_q5_no_gold_or_control_fields(payload)
    return "\n".join(
        [
            "Choose one typed Q5 step using only the authorized runtime context below.",
            "Do not provide chain-of-thought, authorization, or risk fields.",
            "Return JSON only with exactly these fields:",
            '{"kind":"observe|terminal","tool":null,"args":{},"action":null,'
            '"evidence_chunk_ids":[],"reason_code":"short_enum",'
            '"reason_summary":"one sentence"}',
            "RUNTIME_CONTEXT:",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ]
    )


def parse_q5_structured_proposal(
    payload: str | Mapping[str, Any],
) -> Q5StructuredProposal:
    parsed: Any = json.loads(payload) if isinstance(payload, str) else dict(payload)
    return Q5StructuredProposal.model_validate(parsed)


def legal_q5_terminal_actions(
    actor_claims: Q5ActorClaims,
    requested_capability: RequestedCapability,
    *,
    candidates: Iterable[GovernanceAction] | None = None,
) -> list[GovernanceAction]:
    capability_actions = _capability_terminal_actions(requested_capability)
    role_actions = _role_terminal_actions(actor_claims.role)
    allowed = capability_actions & role_actions
    if candidates is not None:
        allowed &= set(candidates)
    return sorted(allowed, key=lambda action: action.value)


def reauthorize_q5_proposal(
    proposal: Q5StructuredProposal,
    *,
    actor_claims: Q5ActorClaims,
    requested_capability: RequestedCapability,
    available_tools: Iterable[Q5ObservationTool] = (),
) -> Q5AuthorizationVerdict:
    """Reauthorize each proposal from current actor claims and capability."""

    role = actor_claims.role.strip().lower()
    if proposal.kind is Q5ProposalKind.observe:
        available = set(available_tools)
        if proposal.tool not in available:
            return _authorization_verdict(
                False,
                "tool_not_available",
                proposal,
                actor_claims,
                requested_capability,
            )
        if role not in _OBSERVATION_ROLES:
            return _authorization_verdict(
                False,
                "observation_role_denied",
                proposal,
                actor_claims,
                requested_capability,
            )
        return _authorization_verdict(
            True,
            "allowed",
            proposal,
            actor_claims,
            requested_capability,
        )

    assert proposal.action is not None
    if proposal.action not in _capability_terminal_actions(requested_capability):
        return _authorization_verdict(
            False,
            "capability_action_denied",
            proposal,
            actor_claims,
            requested_capability,
        )
    if proposal.action not in _role_terminal_actions(role):
        return _authorization_verdict(
            False,
            "role_action_denied",
            proposal,
            actor_claims,
            requested_capability,
        )
    return _authorization_verdict(
        True,
        "allowed",
        proposal,
        actor_claims,
        requested_capability,
    )


def build_q5_context_trace(
    context: Q5DecisionContext,
    *,
    context_version: int,
    proposal: Q5StructuredProposal | None = None,
) -> dict[str, Any]:
    """Build a metadata-first trace without evidence text or grader fields."""

    trace: dict[str, Any] = {
        "context_version": context_version,
        "requested_capability": context.requested_capability.value,
        "resource_refs": list(context.resource_refs),
        "available_tools": [tool.value for tool in context.available_tools],
        "conditions": [condition.value for condition in context.conditions],
        "evidence_decision": context.evidence_decision,
        "authorized_evidence_ids": [
            item.chunk_id for item in context.authorized_evidence
        ],
        "blocked_metadata_ids": [
            item.opaque_chunk_id for item in context.blocked_evidence_metadata
        ],
        "legal_terminal_actions": [
            action.value for action in context.legal_terminal_actions
        ],
        "remaining_observation_budget": context.remaining_observation_budget,
        "remaining_terminal_budget": context.remaining_terminal_budget,
    }
    if proposal is not None:
        trace["proposal"] = proposal.model_dump(mode="json")
    assert_q5_no_gold_or_control_fields(trace)
    return trace


def assert_q5_no_gold_or_control_fields(payload: Any) -> None:
    forbidden = _find_forbidden_keys(payload)
    if forbidden:
        raise ValueError("forbidden Q5 runtime fields: " + ", ".join(sorted(forbidden)))


def _authorized_evidence(
    surviving_chunks: Sequence[RetrievedChunk],
) -> list[Q5AuthorizedEvidence]:
    remaining = Q5_AUTHORIZED_TEXT_CHAR_LIMIT
    evidence: list[Q5AuthorizedEvidence] = []
    seen: set[str] = set()
    for result in surviving_chunks:
        chunk = result.chunk
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        if remaining <= 0:
            break
        excerpt = chunk.text[: min(Q5_EXCERPT_CHAR_LIMIT, remaining)]
        remaining -= len(excerpt)
        evidence.append(
            Q5AuthorizedEvidence(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                text_excerpt=excerpt,
                status=chunk.status.value,
                section_path=list(chunk.section_path),
                source_origin=chunk.source_origin.value,
                corpus_source=chunk.corpus_source.value,
                retrieval_source=result.source.value,
                rerank_score=result.rerank_score,
                relation_summary=_relation_summary(chunk.overlay_relation_note),
            )
        )
    return evidence


def _assert_acl_partition_disjoint(
    surviving_chunks: Sequence[RetrievedChunk],
    blocked_chunks: Sequence[RetrievedChunk],
) -> None:
    surviving_ids = {result.chunk.chunk_id for result in surviving_chunks}
    blocked_ids = {result.chunk.chunk_id for result in blocked_chunks}
    overlap = sorted(surviving_ids & blocked_ids)
    if overlap:
        raise ValueError(
            "ACL surviving_chunks and blocked_chunks overlap: " + ", ".join(overlap)
        )


def _blocked_metadata(
    blocked_chunks: Sequence[RetrievedChunk],
) -> list[Q5BlockedEvidenceMetadata]:
    metadata: list[Q5BlockedEvidenceMetadata] = []
    seen: set[str] = set()
    for result in blocked_chunks:
        chunk_id = result.chunk.chunk_id
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        opaque = hashlib.sha256(f"q5-blocked:{chunk_id}".encode()).hexdigest()
        metadata.append(
            Q5BlockedEvidenceMetadata(
                opaque_chunk_id=f"blocked_{opaque[:24]}",
                block_reason="acl_denied",
            )
        )
    return metadata


def _relation_summary(relation: Any) -> str | None:
    if relation is None:
        return None
    if isinstance(relation, (dict, list)):
        summary = json.dumps(relation, ensure_ascii=False, sort_keys=True, default=str)
    else:
        summary = str(relation)
    return summary[:Q5_RELATION_SUMMARY_CHAR_LIMIT]


def _role_terminal_actions(role: str) -> frozenset[GovernanceAction]:
    normalized = role.strip().lower()
    actions = {GovernanceAction.no_op, GovernanceAction.escalate_to_human}
    for action, roles in DEFAULT_AUTHORIZED_ROLES.items():
        if normalized in roles:
            actions.add(action)
    return frozenset(actions)


def _capability_terminal_actions(
    requested_capability: RequestedCapability,
) -> frozenset[GovernanceAction]:
    return Q5_CAPABILITY_TO_ACTIONS[requested_capability] | _SAFE_TERMINAL_ACTIONS


def _authorization_verdict(
    allowed: bool,
    reason_code: str,
    proposal: Q5StructuredProposal,
    actor_claims: Q5ActorClaims,
    requested_capability: RequestedCapability,
) -> Q5AuthorizationVerdict:
    return Q5AuthorizationVerdict(
        allowed=allowed,
        reason_code=reason_code,
        actor_role=actor_claims.role,
        requested_capability=requested_capability,
        proposal_kind=proposal.kind,
        action=proposal.action,
        tool=proposal.tool,
    )


def _find_forbidden_keys(payload: Any) -> set[str]:
    forbidden: set[str] = set()
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = str(key).strip().lower()
            if (
                normalized in Q5_GOLD_ONLY_FIELDS
                or normalized in _CONTROL_ONLY_FIELDS
                or normalized.startswith("gold_")
            ):
                forbidden.add(normalized)
            forbidden.update(_find_forbidden_keys(value))
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            forbidden.update(_find_forbidden_keys(value))
    return forbidden


def _require_unique(values: Iterable[Any], *, field: str) -> None:
    normalized = [str(value) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")
