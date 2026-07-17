from __future__ import annotations

import pytest

from app.eval.q5_boundary_f_addendum import parser_complexity_attestation_v2
from app.eval.q5_boundary_f_addendum_parser import independent_runtime_challenger_v2
from app.schemas.q5_frontier import FrontierDisposition
from app.schemas.q5_frontier_v6 import PracticalObservationInput, PracticalRuntimeInput


@pytest.mark.parametrize(
    "cue",
    [
        "keep state unchanged",
        "keeps the governed state unchanged",
        "keeping the current governed state unchanged",
        "keep the present governance unchanged",
    ],
)
def test_no_action_morphology_accepts_generic_and_unseen_forms(cue: str) -> None:
    result = independent_runtime_challenger_v2(
        _runtime(
            f"When status signal_900 applies, {cue}; otherwise send the required notice.",
            "signal_900",
        )
    )
    assert result.status == "complete"
    assert result.disposition == FrontierDisposition.no_action


def test_no_action_morphology_does_not_match_unrelated_keep_substrings() -> None:
    result = independent_runtime_challenger_v2(
        _runtime(
            "When status signal_901 applies, bookkeeping remains unchanged; "
            "otherwise send the required notice.",
            "signal_901",
        )
    )
    assert result.status == "abstain"
    assert result.disposition is None


def test_versioned_parser_fails_closed_when_compiled_terminal_is_illegal() -> None:
    result = independent_runtime_challenger_v2(
        _runtime(
            "When status signal_902 applies, keep the governed state unchanged; "
            "otherwise send the required notice.",
            "signal_902",
            legal=[FrontierDisposition.notify, FrontierDisposition.human_review],
        )
    )
    assert result.status == "unsafe"
    assert result.disposition is None


def test_versioned_parser_keeps_host_safety_escalation() -> None:
    result = independent_runtime_challenger_v2(
        _runtime(
            "When status signal_903 applies, keep state unchanged; "
            "otherwise send the required notice.",
            "signal_903",
            authorized=False,
        )
    )
    assert result.status == "complete"
    assert result.disposition == FrontierDisposition.human_review


def test_versioned_parser_complexity_attestation_is_valid() -> None:
    attestation = parser_complexity_attestation_v2()
    assert attestation["valid"] is True
    assert all(attestation["checks"].values())
    assert attestation["measurements"]["forbidden_tokens_found"] == []
    assert attestation["measurements"]["case_specific_literals_found"] == []
    assert attestation["measurements"]["long_literal_count"] == 0


def _runtime(
    policy_text: str,
    status: str,
    *,
    legal: list[FrontierDisposition] | None = None,
    authorized: bool = True,
) -> PracticalRuntimeInput:
    return PracticalRuntimeInput(
        policy_text=policy_text,
        observation=PracticalObservationInput(
            status=status,
            scope="production",
            temporal_state="current",
            exception_active=False,
            authorized=authorized,
            successful=True,
        ),
        legal_dispositions=legal or list(FrontierDisposition),
    )
