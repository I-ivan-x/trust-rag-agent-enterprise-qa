from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.govern.conditions import GovernanceAction
from app.govern.q5_router import (
    Q5MissingStateType,
    Q5RouteFacts,
    Q5RouteReason,
    route_q5,
)


def test_q5_router_rejects_stratum_and_gold_runtime_fields() -> None:
    base = {
        "terminal_policy_block": False,
        "structured_state_complete": False,
        "observable_ambiguity_count": 1,
        "missing_state_types": ["policy_exception"],
        "candidate_terminal_actions": ["escalate_to_human"],
    }
    for forbidden in ("stratum", "gold_action", "gold_secret"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            Q5RouteFacts.model_validate({**base, forbidden: "semantic"})


def test_q5_router_terminal_policy_block_is_deterministic() -> None:
    decision = route_q5(
        Q5RouteFacts(
            terminal_policy_block=True,
            structured_state_complete=False,
            candidate_terminal_actions=[GovernanceAction.escalate_to_human],
        )
    )
    assert decision.route == "rule"
    assert decision.route_reasons == [Q5RouteReason.terminal_policy_block]


def test_q5_router_complete_trusted_state_uses_rule() -> None:
    decision = route_q5(
        Q5RouteFacts(
            structured_state_complete=True,
            candidate_terminal_actions=[GovernanceAction.no_op],
        )
    )
    assert decision.route == "rule"
    assert decision.route_reasons == [Q5RouteReason.trusted_state_complete]


def test_q5_router_missing_runtime_state_uses_llm() -> None:
    decision = route_q5(
        Q5RouteFacts(
            structured_state_complete=False,
            observable_ambiguity_count=2,
            missing_state_types=[
                Q5MissingStateType.policy_exception,
                Q5MissingStateType.incident_impact,
            ],
            candidate_terminal_actions=[
                GovernanceAction.open_remediation_ticket,
                GovernanceAction.escalate_to_human,
            ],
        )
    )
    assert decision.route == "llm"
    assert decision.route_reasons == [
        Q5RouteReason.missing_trusted_state,
        Q5RouteReason.multiple_plausible_outcomes,
    ]
