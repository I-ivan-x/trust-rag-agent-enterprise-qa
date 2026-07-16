from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import preflight_q5_i as preflight


def test_q5_i_preflight_emits_explicit_claim_headroom_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "receipt.json"
    base = {
        "schema_version": "q5-real-preflight-v4",
        "valid": True,
        "request_policy": {
            "completion_requests_sent_during_preflight": 0,
            "http_model_requests_sent_during_preflight": 0,
            "provider_model_calls_during_preflight": 0,
        },
        "historical_verification": [{} for _ in range(7)],
        "errors": [],
    }
    monkeypatch.setattr(preflight, "run_base_preflight", lambda argv: dict(base))
    monkeypatch.setattr(
        preflight,
        "verify_q5_value_ledger",
        lambda run, gold, value: {
            "beneficial_value_capture": 1.0,
            "harmful_terminal_llm_exposure": 0,
            "hybrid_oracle_regret": 0.0,
            "hybrid_observation_planning_llm_calls": 0,
            "hybrid_semantic_binding_llm_calls": 36,
        },
    )
    monkeypatch.setattr(
        preflight,
        "verify_q5_strong_symbolic_artifacts",
        lambda **kwargs: {
            "semantic_success": 1.0,
            "within_policy_pair_success": 1.0,
            "cross_policy_pair_success": 1.0,
        },
    )
    monkeypatch.setattr(
        preflight,
        "q5_read_json",
        lambda path: {
            "by_system": {
                "q5_hybrid_agent": {
                    "trajectory_qualified_success_by_stratum": {"semantic": 0.5},
                    "within_policy_pair_success": 0.333333,
                    "cross_policy_pair_success": 0.0,
                }
            }
        },
    )

    receipt = preflight.main(
        [
            "--mock-run",
            str(tmp_path / "mock"),
            "--value-dir",
            str(tmp_path / "value"),
            "--symbolic-dir",
            str(tmp_path / "symbolic"),
            "--output",
            str(output),
            "--real-run-id",
            "q5-dev-v4-real-i-primary-k3",
        ]
    )

    assert receipt["schema_version"] == "q5-real-preflight-i"
    assert receipt["valid"] is False
    assert "claim_headroom" in receipt["value_frontier"]["claim_readiness"][
        "blockers"
    ]
    assert receipt["request_policy"] == base["request_policy"]
    assert len(receipt["historical_verification"]) == 7
    assert json.loads(output.read_text(encoding="utf-8")) == receipt
