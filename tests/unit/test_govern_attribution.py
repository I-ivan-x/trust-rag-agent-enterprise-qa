from __future__ import annotations

from app.eval.govern_attribution import compute_governance_attribution


def test_per_action_proposed_correct_false() -> None:
    attribution = compute_governance_attribution(
        [],
        [
            _row(
                "case-1",
                proposed_action="open_remediation_ticket",
                gold_action="open_remediation_ticket",
            ),
            _row(
                "case-2",
                proposed_action="open_remediation_ticket",
                gold_action="flag_stale",
            ),
        ],
    )

    assert attribution is not None
    ticket = attribution["per_action"]["open_remediation_ticket"]
    assert ticket["proposed_count"] == 2
    assert ticket["correct_count"] == 1
    assert ticket["false_trigger_count"] == 1


def test_blocked_count_on_forced_escalate() -> None:
    attribution = compute_governance_attribution(
        [],
        [
            _row(
                "case-1",
                proposed_action="open_remediation_ticket",
                gold_action="open_remediation_ticket",
                validator_ok=False,
                forced_action="escalate_to_human",
            )
        ],
    )

    assert attribution is not None
    assert attribution["per_action"]["open_remediation_ticket"]["blocked_count"] == 1


def test_f11_zero_when_evidence_guarded() -> None:
    attribution = compute_governance_attribution(
        [],
        [
            _row(
                "case-1",
                proposed_action="escalate_to_human",
                gold_action="escalate_to_human",
                gold_condition="INSUFFICIENT_EVIDENCE",
                evidence_decision="insufficient",
                executed_side_effect=False,
            )
        ],
    )

    assert attribution is not None
    assert attribution["failure_taxonomy"]["F11_action_without_evidence"] == 0


def test_f13_zero_when_unauth_guarded() -> None:
    attribution = compute_governance_attribution(
        [],
        [
            _row(
                "case-1",
                proposed_action="escalate_to_human",
                gold_action="escalate_to_human",
                authorized=False,
                executed_side_effect=False,
            )
        ],
    )

    assert attribution is not None
    assert attribution["failure_taxonomy"]["F13_missed_escalation_unauth"] == 0


def test_f10_wrong_action() -> None:
    attribution = compute_governance_attribution(
        [],
        [
            _row(
                "case-1",
                proposed_action="flag_stale",
                gold_action="open_remediation_ticket",
            )
        ],
    )

    assert attribution is not None
    assert attribution["failure_taxonomy"]["F10_wrong_action_selected"] == 1


def _row(
    case_id: str,
    *,
    proposed_action: str,
    gold_action: str,
    system_name: str = "final_governed_rule",
    authorized: bool = True,
    gold_condition: str = "CONFIG_VIOLATION",
    evidence_decision: str = "sufficient",
    executed_side_effect: bool = False,
    validator_ok: bool = True,
    forced_action: str | None = None,
) -> dict:
    return {
        "case_id": case_id,
        "system_name": system_name,
        "run_index": 1,
        "split": "external",
        "gold_action": gold_action,
        "gold_condition": gold_condition,
        "authorized": authorized,
        "expected_tier": "approval",
        "detected_conditions": [],
        "authorized_actor": authorized,
        "evidence_decision": evidence_decision,
        "proposed_action": proposed_action,
        "controller_source": "rule",
        "risk_tier": "approval",
        "validator_ok": validator_ok,
        "forced_action": forced_action,
        "approval_state": "none",
        "executed_side_effect": executed_side_effect,
        "sink_record_id": None,
    }
