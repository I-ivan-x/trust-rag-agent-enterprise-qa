from __future__ import annotations

from types import SimpleNamespace

from app.agent.actions import ActionProposal, execute_action, materialize_proposal
from app.agent.controller import RuleController
from app.agent.diagnosis import ActionType, DiagnosisReport, FailureType
from app.agent.validator import ActionBudget, validate
from app.core.enums import AccessLevel, DocumentStatus
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.rerank.reranker import MockReranker
from app.schemas.retrieval import RetrievalOptions
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


def test_rule_controller_branches_and_cooccurrence_prefers_b() -> None:
    controller = RuleController()

    assert (
        controller.select(
            _diag(FailureType.permission_blocked, [ActionType.refuse_with_explanation])
        ).action
        == ActionType.refuse_with_explanation
    )
    assert (
        controller.select(
            _diag(
                FailureType.conflict,
                [ActionType.present_conflict_set, ActionType.refuse_with_explanation],
            )
        ).action
        == ActionType.present_conflict_set
    )
    assert (
        controller.select(
            _diag(
                FailureType.policy_and_weak_recall,
                [
                    ActionType.rewrite_query,
                    ActionType.filtered_retrieval,
                    ActionType.refuse_with_explanation,
                ],
            )
        ).action
        == ActionType.filtered_retrieval
    )
    assert (
        controller.select(
            _diag(
                FailureType.weak_recall,
                [ActionType.rewrite_query, ActionType.refuse_with_explanation],
            )
        ).action
        == ActionType.rewrite_query
    )
    assert (
        controller.select(
            _diag(
                FailureType.policy_crowding,
                [ActionType.filtered_retrieval, ActionType.refuse_with_explanation],
            )
        ).action
        == ActionType.filtered_retrieval
    )
    assert (
        controller.select(
            _diag(FailureType.no_recovery, [ActionType.refuse_with_explanation])
        ).action
        == ActionType.refuse_with_explanation
    )


def test_validator_rejects_illegal_action_and_budget_exhaustion() -> None:
    diagnosis = _diag(
        FailureType.weak_recall,
        [ActionType.rewrite_query, ActionType.refuse_with_explanation],
    )

    illegal = validate(
        ActionProposal(
            action=ActionType.filtered_retrieval, args={"filters": {"status": "active"}}
        ),
        diagnosis,
        ActionBudget(),
    )
    exhausted = validate(
        ActionProposal(
            action=ActionType.rewrite_query,
            args={
                "rewritten_query": "refresh token",
                "_allowed_entity_terms": ["refresh", "token"],
            },
        ),
        diagnosis,
        ActionBudget(max_nonterminal_actions=1, consumed_nonterminal_actions=1),
    )

    assert illegal.ok is False
    assert illegal.reject_reason == "action_not_legal_for_diagnosis"
    assert exhausted.ok is False
    assert exhausted.reject_reason == "budget_exhausted"


def test_validator_rejects_permission_recovery_and_filter_widening() -> None:
    permission = _diag(
        FailureType.permission_blocked,
        [ActionType.refuse_with_explanation, ActionType.filtered_retrieval],
    )
    assert (
        validate(
            ActionProposal(
                action=ActionType.filtered_retrieval, args={"filters": {"status": "active"}}
            ),
            permission,
            ActionBudget(),
        ).reject_reason
        == "permission_blocked_requires_refusal"
    )

    policy = _diag(
        FailureType.policy_crowding,
        [ActionType.filtered_retrieval, ActionType.refuse_with_explanation],
    )
    assert (
        validate(
            ActionProposal(
                action=ActionType.filtered_retrieval,
                args={"filters": {"access_level": "restricted"}},
            ),
            policy,
            ActionBudget(),
        ).reject_reason
        == "filter_field_not_allowed:access_level"
    )
    assert (
        validate(
            ActionProposal(
                action=ActionType.filtered_retrieval, args={"filters": {"status": "deprecated"}}
            ),
            policy,
            ActionBudget(),
        ).reject_reason
        == "status_filter_must_only_allow_active"
    )


def test_validator_enforces_rewrite_entity_subset() -> None:
    diagnosis = _diag(
        FailureType.weak_recall,
        [ActionType.rewrite_query, ActionType.refuse_with_explanation],
    )

    rejected = validate(
        ActionProposal(
            action=ActionType.rewrite_query,
            args={
                "rewritten_query": "secret payroll export",
                "_allowed_entity_terms": ["refresh", "token"],
            },
        ),
        diagnosis,
        ActionBudget(),
    )
    accepted = validate(
        ActionProposal(
            action=ActionType.rewrite_query,
            args={
                "rewritten_query": "refresh token limit",
                "_allowed_entity_terms": ["refresh", "token", "limit"],
            },
        ),
        diagnosis,
        ActionBudget(),
    )

    assert rejected.ok is False
    assert rejected.reject_reason == "rewrite_entities_not_allowed:export,payroll,secret"
    assert accepted.ok is True


def test_materialized_rewrite_uses_query_rewriter_and_entity_allowlist() -> None:
    retrieved = make_retrieved_chunk("chunk", "refresh token rate limit")
    pass_result = _pass_result([retrieved], acl_surviving=[retrieved], entity_miss=True)

    proposal = materialize_proposal(
        ActionProposal(action=ActionType.rewrite_query, args={}),
        query="refresh rlimit for auth?",
        pass_result=pass_result,
    )
    diagnosis = _diag(
        FailureType.weak_recall,
        [ActionType.rewrite_query, ActionType.refuse_with_explanation],
    )

    assert proposal.args["rewritten_query"] == "refresh token rate limit for auth?"
    assert validate(proposal, diagnosis, ActionBudget()).ok is True


def test_filtered_retrieval_action_still_regates_restricted_chunks() -> None:
    restricted = make_retrieved_chunk(
        "restricted",
        "restricted admin key",
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
    )
    active = make_retrieved_chunk("active", "active public token limit")
    retriever = _FakeRetriever([restricted, active])

    result = execute_action(
        ActionProposal(
            action=ActionType.filtered_retrieval,
            args={"filters": {"status": "active", "exclude_doc_ids": []}},
        ),
        "What is the token limit?",
        retriever,
        MockReranker(),
        SimpleNamespace(),
        retrieval_options=RetrievalOptions(top_k_dense=0, top_k_sparse=2, top_n_rerank=2),
        user_role="employee",
        user_clearance="internal",
    )

    assert result.pass_result is not None
    blocked_ids = {item.chunk.chunk_id for item in result.pass_result.acl_decision.blocked_chunks}
    surviving_ids = {
        item.chunk.chunk_id for item in result.pass_result.acl_decision.surviving_chunks
    }
    assert restricted.chunk.chunk_id in blocked_ids
    assert restricted.chunk.chunk_id not in surviving_ids


def _diag(failure_type: FailureType, legal_actions: list[ActionType]) -> DiagnosisReport:
    return DiagnosisReport(
        evidence_decision="insufficient",
        permission_blocked_count=0,
        deprecated_neighbor_count=0,
        restricted_neighbor_count=0,
        conflict_group_ids=[],
        clean_active_count=0,
        top_rerank_score=0.1,
        support_chunk_count=0,
        entity_miss=True,
        failure_type=failure_type,
        legal_actions=legal_actions,
    )


def _pass_result(
    reranked,
    *,
    acl_surviving=None,
    acl_blocked=None,
    deprecated=None,
    entity_miss: bool = False,
) -> RetrievalPassResult:
    return RetrievalPassResult(
        query="What is the token limit?",
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
            evidence_sufficient=False,
            reason="entity_miss" if entity_miss else "test",
            support_count=0,
            entity_miss=entity_miss,
        ),
    )


class _FakeRetriever:
    def __init__(self, chunks) -> None:
        self.chunks = chunks
        self.last_warnings = []

    def retrieve(self, query, options, filters=None):
        del query, options
        results = self.chunks
        if filters and filters.get("exclude_doc_ids"):
            excluded = set(filters["exclude_doc_ids"])
            results = [item for item in results if item.chunk.doc_id not in excluded]
        if filters and filters.get("status") == "active":
            results = [item for item in results if item.chunk.status == DocumentStatus.active]
        return results
