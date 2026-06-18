from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import AccessLevel
from app.schemas.retrieval import RetrievedChunk
from app.workflow.state import RetrievalPassResult


class ActionType(StrEnum):
    rewrite_query = "rewrite_query"
    filtered_retrieval = "filtered_retrieval"
    present_conflict_set = "present_conflict_set"
    refuse_with_explanation = "refuse_with_explanation"


class FailureType(StrEnum):
    permission_blocked = "PERMISSION_BLOCKED"
    conflict = "CONFLICT"
    policy_and_weak_recall = "POLICY_CROWDING_AND_WEAK_RECALL"
    policy_crowding = "POLICY_CROWDING"
    weak_recall = "WEAK_RECALL"
    no_recovery = "NO_RECOVERY"


class DiagnosisReport(BaseModel):
    evidence_decision: Literal["sufficient", "insufficient"]
    permission_blocked_count: int = Field(ge=0)
    deprecated_neighbor_count: int = Field(ge=0)
    restricted_neighbor_count: int = Field(ge=0)
    conflict_group_ids: list[str] = Field(default_factory=list)
    clean_active_count: int = Field(ge=0)
    top_rerank_score: float | None = None
    support_chunk_count: int = Field(ge=0)
    entity_miss: bool = False
    failure_type: FailureType
    legal_actions: list[ActionType] = Field(default_factory=list)


# TODO-W7: calibrate these against Phase 1/Week 7 distributions. Keep the
# placeholder support line at >=2 so policy crowding can mean "some clean
# evidence exists, but not enough yet" rather than "no clean evidence exists."
DEFAULT_MIN_SUPPORT = 2
DEFAULT_MIN_SCORE = 0.3


def diagnose(
    pass_result: RetrievalPassResult,
    *,
    min_support: int = DEFAULT_MIN_SUPPORT,
    min_score: float = DEFAULT_MIN_SCORE,
) -> DiagnosisReport:
    evidence_sufficient = pass_result.evidence_decision.evidence_sufficient
    evidence_decision: Literal["sufficient", "insufficient"] = (
        "sufficient" if evidence_sufficient else "insufficient"
    )
    permission_blocked_count = len(pass_result.acl_decision.blocked_chunks)
    deprecated_neighbor_count = len(pass_result.state_decision.deprecated_chunks)
    restricted_neighbor_count = _restricted_neighbor_count(pass_result.reranked_chunks)
    clean_active_count = len(pass_result.acl_decision.surviving_chunks)
    top_rerank_score = _top_score(pass_result.reranked_chunks)
    support_chunk_count = pass_result.evidence_decision.support_count
    entity_miss = pass_result.evidence_decision.entity_miss
    conflict_group_ids = _conflict_group_ids(pass_result)

    if evidence_sufficient:
        return DiagnosisReport(
            evidence_decision=evidence_decision,
            permission_blocked_count=permission_blocked_count,
            deprecated_neighbor_count=deprecated_neighbor_count,
            restricted_neighbor_count=restricted_neighbor_count,
            conflict_group_ids=conflict_group_ids,
            clean_active_count=clean_active_count,
            top_rerank_score=top_rerank_score,
            support_chunk_count=support_chunk_count,
            entity_miss=entity_miss,
            failure_type=FailureType.no_recovery,
            legal_actions=[],
        )

    if permission_blocked_count > 0 and clean_active_count < min_support:
        return _report(
            evidence_decision=evidence_decision,
            permission_blocked_count=permission_blocked_count,
            deprecated_neighbor_count=deprecated_neighbor_count,
            restricted_neighbor_count=restricted_neighbor_count,
            conflict_group_ids=conflict_group_ids,
            clean_active_count=clean_active_count,
            top_rerank_score=top_rerank_score,
            support_chunk_count=support_chunk_count,
            entity_miss=entity_miss,
            failure_type=FailureType.permission_blocked,
            legal_actions=[ActionType.refuse_with_explanation],
        )

    if conflict_group_ids:
        return _report(
            evidence_decision=evidence_decision,
            permission_blocked_count=permission_blocked_count,
            deprecated_neighbor_count=deprecated_neighbor_count,
            restricted_neighbor_count=restricted_neighbor_count,
            conflict_group_ids=conflict_group_ids,
            clean_active_count=clean_active_count,
            top_rerank_score=top_rerank_score,
            support_chunk_count=support_chunk_count,
            entity_miss=entity_miss,
            failure_type=FailureType.conflict,
            legal_actions=[
                ActionType.present_conflict_set,
                ActionType.refuse_with_explanation,
            ],
        )

    signal_policy_crowding = (
        deprecated_neighbor_count + restricted_neighbor_count >= 2
        and 0 < clean_active_count < min_support
    )
    signal_weak_recall = entity_miss or (
        top_rerank_score is not None and top_rerank_score < min_score
    )

    if signal_policy_crowding and signal_weak_recall:
        failure_type = FailureType.policy_and_weak_recall
        legal_actions = [
            ActionType.rewrite_query,
            ActionType.filtered_retrieval,
            ActionType.refuse_with_explanation,
        ]
    elif signal_policy_crowding:
        failure_type = FailureType.policy_crowding
        legal_actions = [
            ActionType.filtered_retrieval,
            ActionType.refuse_with_explanation,
        ]
    elif signal_weak_recall:
        failure_type = FailureType.weak_recall
        legal_actions = [
            ActionType.rewrite_query,
            ActionType.refuse_with_explanation,
        ]
    else:
        failure_type = FailureType.no_recovery
        legal_actions = [ActionType.refuse_with_explanation]

    return _report(
        evidence_decision=evidence_decision,
        permission_blocked_count=permission_blocked_count,
        deprecated_neighbor_count=deprecated_neighbor_count,
        restricted_neighbor_count=restricted_neighbor_count,
        conflict_group_ids=conflict_group_ids,
        clean_active_count=clean_active_count,
        top_rerank_score=top_rerank_score,
        support_chunk_count=support_chunk_count,
        entity_miss=entity_miss,
        failure_type=failure_type,
        legal_actions=legal_actions,
    )


def _report(**kwargs) -> DiagnosisReport:
    return DiagnosisReport(**kwargs)


def _restricted_neighbor_count(chunks: list[RetrievedChunk]) -> int:
    return sum(chunk.chunk.access_level == AccessLevel.restricted for chunk in chunks)


def _conflict_group_ids(pass_result: RetrievalPassResult) -> list[str]:
    group_id = pass_result.conflict_decision.conflict_group_id
    if group_id:
        return [group_id]
    grouped: dict[str, set[str]] = {}
    for result in pass_result.reranked_chunks:
        chunk = result.chunk
        if chunk.status.value != "active" or not chunk.conflict_group_id:
            continue
        grouped.setdefault(chunk.conflict_group_id, set()).add(chunk.doc_id)
    return sorted(group_id for group_id, doc_ids in grouped.items() if len(doc_ids) >= 2)


def _top_score(chunks: list[RetrievedChunk]) -> float | None:
    scores: list[float] = []
    for result in chunks:
        for score in (
            result.rerank_score,
            result.rrf_score,
            result.vector_score,
            result.keyword_score,
        ):
            if score is not None:
                scores.append(float(score))
                break
    return max(scores) if scores else None
