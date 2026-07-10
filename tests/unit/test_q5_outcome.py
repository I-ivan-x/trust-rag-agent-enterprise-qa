from __future__ import annotations

from app.eval.q5_outcome import (
    apply_q5_environment_transition,
    grade_q5_final_state,
    q5_outcome_environment_from_runtime,
)
from app.govern.conditions import GovernanceAction, RiskTier
from app.govern.sinks import ActionRecord
from app.schemas.q5_task import Q5EnvironmentState


def _environment():
    return q5_outcome_environment_from_runtime(
        Q5EnvironmentState(
            environment_ref="q5-p4-env",
            policy_exceptions={},
            change_states={},
            incident_impacts={},
            initial_records=[{"record_id": "existing", "action": "flag_stale"}],
            pending_queue=[],
        )
    )


def _record(
    action: GovernanceAction,
    approval_state: str,
    *,
    record_id: str,
) -> ActionRecord:
    risk_tier = {
        "committed": RiskTier.auto,
        "pending_approval": RiskTier.approval,
        "escalated": RiskTier.terminal,
    }[approval_state]
    return ActionRecord(
        record_id=record_id,
        action=action,
        condition=None,
        doc_ids=["doc-1"],
        evidence_citations=["chunk-1"],
        actor_role="admin",
        risk_tier=risk_tier,
        approval_state=approval_state,
        dedup_key=f"dedup-{record_id}",
        created_at="1970-01-01T00:00:00+00:00",
    )


def test_q5_committed_side_effect_updates_records_on_isolated_copy() -> None:
    before = _environment()
    after, transition = apply_q5_environment_transition(
        before,
        action=GovernanceAction.flag_stale,
        record=_record(
            GovernanceAction.flag_stale,
            "committed",
            record_id="committed-1",
        ),
    )

    assert transition.valid is True
    assert transition.committed_side_effect is True
    assert [item["record_id"] for item in after.records] == ["existing", "committed-1"]
    assert after.pending_queue == []
    assert [item["record_id"] for item in before.records] == ["existing"]


def test_q5_pending_approval_updates_only_pending_queue() -> None:
    before = _environment()
    after, transition = apply_q5_environment_transition(
        before,
        action=GovernanceAction.open_remediation_ticket,
        record=_record(
            GovernanceAction.open_remediation_ticket,
            "pending_approval",
            record_id="pending-1",
        ),
    )

    assert transition.transition == "pending_approval"
    assert transition.committed_side_effect is False
    assert after.records == before.records
    assert [item["record_id"] for item in after.pending_queue] == ["pending-1"]


def test_q5_escalation_and_no_op_never_forge_side_effects() -> None:
    before = _environment()
    escalated, escalation = apply_q5_environment_transition(
        before,
        action=GovernanceAction.escalate_to_human,
        record=_record(
            GovernanceAction.escalate_to_human,
            "escalated",
            record_id="escalation-1",
        ),
    )
    no_op, no_op_transition = apply_q5_environment_transition(
        before,
        action=GovernanceAction.no_op,
        record=None,
    )

    assert escalation.transition == "escalated"
    assert no_op_transition.transition == "no_op"
    assert escalated.records == no_op.records == before.records
    assert escalated.pending_queue == no_op.pending_queue == []


def test_q5_invalid_transition_is_rejected_without_state_mutation() -> None:
    before = _environment()
    after, transition = apply_q5_environment_transition(
        before,
        action=GovernanceAction.flag_stale,
        record=_record(
            GovernanceAction.open_remediation_ticket,
            "pending_approval",
            record_id="mismatch-1",
        ),
    )

    assert transition.valid is False
    assert transition.transition == "invalid"
    assert after == before


def test_q5_final_state_grader_uses_assertions_not_agent_claims() -> None:
    before = _environment()
    after, _ = apply_q5_environment_transition(
        before,
        action=GovernanceAction.flag_stale,
        record=_record(
            GovernanceAction.flag_stale,
            "committed",
            record_id="committed-1",
        ),
    )
    passing = grade_q5_final_state(
        [
            {
                "path": "records",
                "operator": "contains",
                "value": {
                    "record_id": "committed-1",
                    "action": "flag_stale",
                    "approval_state": "committed",
                },
            },
            {"path": "pending_queue", "operator": "unchanged"},
        ],
        before=before,
        after=after,
    )
    failing = grade_q5_final_state(
        [
            {
                "path": "records",
                "operator": "contains",
                "value": {"action": "send_alert"},
            }
        ],
        before=before,
        after=after,
    )

    assert passing.task_success is True
    assert failing.task_success is False
