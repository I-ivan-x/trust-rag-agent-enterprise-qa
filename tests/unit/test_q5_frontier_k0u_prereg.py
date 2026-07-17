from __future__ import annotations

import json
from pathlib import Path

from app.eval.q5_frontier_k0u_prereg import (
    parser_complexity_attestation,
    verify_k0u_preregistration,
    write_k0u_preregistration,
)
from app.eval.q5_frontier_k0u_prereg_parser import preregistered_practical_parser
from app.schemas.q5_frontier import FrontierDisposition
from app.schemas.q5_frontier_v6 import PracticalObservationInput, PracticalRuntimeInput


def _runtime(text: str, *, status: str = "signal_alpha") -> PracticalRuntimeInput:
    return PracticalRuntimeInput(
        policy_text=text,
        observation=PracticalObservationInput(
            status=status,
            scope="production",
            temporal_state="current",
            exception_active=False,
            authorized=True,
            successful=True,
        ),
        legal_dispositions=list(FrontierDisposition),
    )


def _policy(value: str = "signal_alpha") -> str:
    return "\n".join(
        [
            "Scope rule: production,restricted.",
            "Time rule: current.",
            f"Condition all: status eq {value}, scope eq production.",
            "Condition any: none.",
            "On match: initiate corrective handling.",
            "On miss: issue the required notice.",
            "Exception active: request authorized human judgment.",
            "Precedence: exception_overrides.",
        ]
    )


def test_practical_parser_genericity_metamorphics() -> None:
    base = _policy()
    assert preregistered_practical_parser(_runtime(base)).disposition == "remediate"
    renamed = _policy("signal_renamed")
    assert (
        preregistered_practical_parser(_runtime(renamed, status="signal_renamed")).disposition
        == "remediate"
    )
    reordered = "\n".join(reversed(base.splitlines()))
    assert preregistered_practical_parser(_runtime(reordered)).disposition == "remediate"
    distracted = "An unrelated audit note has no operative force.\n" + base
    assert preregistered_practical_parser(_runtime(distracted)).disposition == "remediate"
    unknown = base.replace("Condition all:", "Whenever perhaps:")
    assert preregistered_practical_parser(_runtime(unknown)).status == "abstain"


def test_practical_parser_runtime_safety_guard() -> None:
    runtime = _runtime(_policy()).model_copy(
        update={
            "observation": _runtime(_policy()).observation.model_copy(
                update={"authorized": False}
            )
        }
    )
    result = preregistered_practical_parser(runtime)
    assert result.disposition == "human_review"


def test_complexity_budget_and_forbidden_inputs_are_mechanical() -> None:
    receipt = parser_complexity_attestation()
    assert receipt["valid"] is True
    assert all(receipt["checks"].values())
    assert receipt["measurements"]["forbidden_tokens_found"] == []
    assert receipt["measurements"]["long_literal_count"] == 0


def test_k0u_prereg_package_has_no_authoring_or_labels(tmp_path: Path) -> None:
    target = tmp_path / "prereg"
    write_k0u_preregistration(target)
    verify_k0u_preregistration(target)
    names = {item.name for item in target.iterdir()}
    assert not names & {
        "runtime_cases.jsonl",
        "environment_authoring.jsonl",
        "sealed_labels.jsonl",
        "semantic_representation.jsonl",
        "evaluation_groups.jsonl",
    }
    gates = json.loads((target / "k1_gates.json").read_text())
    assert gates["oracle_resolvable_abstentions_min"] == 24
    assert gates["hybrid_theoretical_call_avoidance_min"] == 0.4
