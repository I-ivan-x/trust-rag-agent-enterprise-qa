from __future__ import annotations

import json

from app.eval.q5_mock import Q5DeterministicMockPolicyModel


def test_q5_mock_uses_policy_exception_scope_from_runtime_facts() -> None:
    proposal = _second_step(
        conditions=["CONFIG_VIOLATION"],
        query="Review the production exporter exception.",
        legal_actions=["open_remediation_ticket", "escalate_to_human"],
        observation={
            "tool_name": "lookup_policy_exception",
            "status": "ok",
            "observation": {
                "observation_type": "policy_exception",
                "resource_ref": "resource:exporter",
                "policy_ref": "policy:change-control",
                "status": "active",
                "scope": "staging",
            },
        },
    )

    assert proposal["decision_basis"]["policy_disposition"] == "remediate"


def test_q5_mock_treats_planned_and_completed_change_states_differently() -> None:
    planned = _second_step(
        conditions=["STALE_PROCEDURE"],
        query="Review the runbook migration.",
        legal_actions=["flag_stale", "escalate_to_human"],
        observation={
            "tool_name": "inspect_change_state",
            "status": "ok",
            "observation": {
                "observation_type": "change_state",
                "change_ref": "change:runbook-v2",
                "status": "planned",
            },
        },
    )
    completed = _second_step(
        conditions=["STALE_PROCEDURE"],
        query="Review the runbook migration.",
        legal_actions=["flag_stale", "escalate_to_human"],
        observation={
            "tool_name": "inspect_change_state",
            "status": "ok",
            "observation": {
                "observation_type": "change_state",
                "change_ref": "change:runbook-v2",
                "status": "completed",
            },
        },
    )

    assert planned["decision_basis"]["policy_disposition"] == "human_review"
    assert completed["decision_basis"]["policy_disposition"] == "mark_stale"


def test_q5_mock_does_not_send_production_alert_for_staging_impact() -> None:
    proposal = _second_step(
        conditions=["ACTIVE_ACTIVE_CONFLICT"],
        query="Inspect staging routing impact.",
        legal_actions=["send_alert", "escalate_to_human"],
        observation={
            "tool_name": "inspect_incident_impact",
            "status": "ok",
            "observation": {
                "observation_type": "incident_impact",
                "resource_ref": "resource:routing-staging",
                "status": "outage",
            },
        },
    )

    assert proposal["decision_basis"]["policy_disposition"] == "human_review"


def test_q5_mock_keeps_deterministic_conflict_action_without_probe() -> None:
    context = _context(
        conditions=["ACTIVE_ACTIVE_CONFLICT"],
        query="Send an alert for duplicate production routing.",
        legal_actions=["send_alert", "escalate_to_human"],
    )

    proposal = _generate(context)

    assert proposal["decision_basis"]["policy_disposition"] == "notify"


def _second_step(
    *,
    conditions: list[str],
    query: str,
    legal_actions: list[str],
    observation: dict,
) -> dict:
    context = _context(
        conditions=conditions,
        query=query,
        legal_actions=legal_actions,
    )
    context["observations"] = [observation]
    return _generate(context)


def _context(
    *,
    conditions: list[str],
    query: str,
    legal_actions: list[str],
) -> dict:
    return {
        "query": query,
        "conditions": conditions,
        "observations": [],
        "available_tools": [],
        "legal_terminal_actions": legal_actions,
        "authorized_evidence": [{"chunk_id": "chunk-runtime"}],
        "resource_refs": [
            "resource:exporter",
            "policy:change-control",
            "change:runbook-v2",
        ],
        "evidence_decision": "sufficient",
    }


def _generate(context: dict) -> dict:
    prompt = "Q5\nRUNTIME_CONTEXT:\n" + json.dumps(context, sort_keys=True)
    return json.loads(Q5DeterministicMockPolicyModel().generate(prompt))
