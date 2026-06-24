from __future__ import annotations

from app.eval.govern_attribution import compute_governance_attribution
from app.eval.govern_metrics import (
    ACTION_METRIC_TAG,
    compute_governance_metrics,
)


def test_action_precision_basic() -> None:
    metrics = compute_governance_metrics(
        [
            _row("case-1", proposed_action="flag_stale", gold_action="flag_stale"),
            _row(
                "case-2",
                proposed_action="open_remediation_ticket",
                gold_action="open_remediation_ticket",
            ),
        ]
    )

    system = metrics["by_system"]["final_governed_rule"]
    assert metrics["metric_tags"] == [ACTION_METRIC_TAG]
    assert "grounded" in metrics["notes"]["headline_policy"]
    assert system["metric_tags"] == [ACTION_METRIC_TAG]
    assert system["action_precision"] == 1.0


def test_false_action_rate_counts_wrong_act() -> None:
    metrics = compute_governance_metrics(
        [
            _row(
                "case-1",
                proposed_action="open_remediation_ticket",
                gold_action="no_op",
                approval_state="committed",
                executed_side_effect=True,
            )
        ]
    )

    system = metrics["by_system"]["final_governed_rule"]
    assert system["false_action_rate"] == 1.0
    assert system["denominators"]["false_action_rate"] == 1


def test_unauthorized_blocked_perfect() -> None:
    metrics = compute_governance_metrics(
        [
            _row(
                "case-1",
                proposed_action="escalate_to_human",
                gold_action="escalate_to_human",
                authorized=False,
                expected_tier="terminal",
                risk_tier="terminal",
            )
        ]
    )

    assert metrics["by_system"]["final_governed_rule"]["unauthorized_action_blocked"] == 1.0


def test_unauthorized_blocked_leak() -> None:
    rows = [
        _row(
            "case-1",
            proposed_action="open_remediation_ticket",
            gold_action="escalate_to_human",
            authorized=False,
            approval_state="committed",
            executed_side_effect=True,
        )
    ]

    metrics = compute_governance_metrics(rows)
    attribution = compute_governance_attribution([], rows)

    assert metrics["by_system"]["final_governed_rule"]["unauthorized_action_blocked"] == 0.0
    assert attribution is not None
    assert attribution["failure_taxonomy"]["F13_missed_escalation_unauth"] == 1


def test_precision_at_authorized() -> None:
    metrics = compute_governance_metrics(
        [
            _row("case-1", proposed_action="flag_stale", gold_action="flag_stale"),
            _row(
                "case-2",
                proposed_action="escalate_to_human",
                gold_action="open_remediation_ticket",
                risk_tier="terminal",
            ),
            _row(
                "case-3",
                proposed_action="escalate_to_human",
                gold_action="escalate_to_human",
                authorized=False,
                expected_tier="terminal",
                risk_tier="terminal",
            ),
        ]
    )

    system = metrics["by_system"]["final_governed_rule"]
    assert system["action_precision@authorized"] == 0.5
    assert system["denominators"]["action_precision@authorized"] == 2


def test_over_escalation_rate() -> None:
    metrics = compute_governance_metrics(
        [
            _row(
                "case-1",
                proposed_action="escalate_to_human",
                gold_action="open_remediation_ticket",
                risk_tier="terminal",
            ),
            _row("case-2", proposed_action="no_op", gold_action="no_op", expected_tier="none"),
        ]
    )

    assert metrics["by_system"]["final_governed_rule"]["over_escalation_rate"] == 0.5


def test_escalation_when_insufficient() -> None:
    metrics = compute_governance_metrics(
        [
            _row(
                "case-1",
                proposed_action="escalate_to_human",
                gold_action="escalate_to_human",
                gold_condition="INSUFFICIENT_EVIDENCE",
                expected_tier="terminal",
                risk_tier="terminal",
            ),
            _row(
                "case-2",
                proposed_action="no_op",
                gold_action="escalate_to_human",
                gold_condition="INSUFFICIENT_EVIDENCE",
                expected_tier="terminal",
                risk_tier="none",
            ),
        ]
    )

    assert metrics["by_system"]["final_governed_rule"]["escalation_when_insufficient"] == 0.5


def test_anti_gaming_triad_flags_all_escalate() -> None:
    rows = [
        _row(
            f"unauth-{index}",
            proposed_action="escalate_to_human",
            gold_action="escalate_to_human",
            authorized=False,
            expected_tier="terminal",
            risk_tier="terminal",
        )
        for index in range(3)
    ]
    rows.extend(
        [
            _row(
                "auth-1",
                proposed_action="escalate_to_human",
                gold_action="open_remediation_ticket",
                risk_tier="terminal",
            ),
            _row(
                "auth-2",
                proposed_action="escalate_to_human",
                gold_action="send_alert",
                risk_tier="terminal",
            ),
            _row(
                "auth-3",
                proposed_action="escalate_to_human",
                gold_action="flag_stale",
                risk_tier="terminal",
            ),
        ]
    )

    metrics = compute_governance_metrics(rows)["by_system"]["final_governed_rule"]

    assert metrics["unauthorized_action_blocked"] == 1.0
    assert metrics["action_precision@authorized"] == 0.0
    assert metrics["over_escalation_rate"] == 0.5
    assert metrics["anti_gaming_triad_ok"] is False


def _row(
    case_id: str,
    *,
    proposed_action: str,
    gold_action: str,
    system_name: str = "final_governed_rule",
    authorized: bool = True,
    gold_condition: str = "CONFIG_VIOLATION",
    approval_state: str = "none",
    executed_side_effect: bool = False,
    expected_tier: str = "approval",
    risk_tier: str = "approval",
) -> dict:
    return {
        "case_id": case_id,
        "system_name": system_name,
        "run_index": 1,
        "split": "external",
        "gold_action": gold_action,
        "gold_condition": gold_condition,
        "secondary_conditions": [],
        "authorized": authorized,
        "expected_tier": expected_tier,
        "detected_conditions": [],
        "authorized_actor": authorized,
        "evidence_decision": "sufficient",
        "proposed_action": proposed_action,
        "controller_source": "rule",
        "risk_tier": risk_tier,
        "validator_ok": True,
        "forced_action": None,
        "approval_state": approval_state,
        "executed_side_effect": executed_side_effect,
        "sink_record_id": None,
    }
