from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval.q5_boundary_e import (
    runtime_compositional_challenger_k0u,
    verify_boundary_e,
    write_boundary_e,
)


def test_boundary_e_closes_k0t_covered_and_uncovered_32_each(tmp_path: Path) -> None:
    target = tmp_path / "boundary-e"
    summary = write_boundary_e(target)
    assert verify_boundary_e(target) == summary
    assert summary["results"] == {
        "parser_covered": {"case_count": 32, "parsed_count": 32, "correct_count": 32},
        "parser_uncovered": {"case_count": 32, "parsed_count": 32, "correct_count": 32},
    }
    assert summary["fixed_conclusion"] == "K0T 四模板仍属于 deterministic frontier"
    assert summary["prior_readiness_revoked"] is True
    assert summary["k1_approved"] is False


def test_runtime_challenger_has_closed_input_and_fails_unknown_text() -> None:
    assert runtime_compositional_challenger_k0u("unknown policy", "signal_100") is None
    with pytest.raises(TypeError):
        runtime_compositional_challenger_k0u(  # type: ignore[call-arg]
            policy_text="unknown", observed_status="x", gold="notify"
        )


def test_boundary_e_rehashed_mutation_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "boundary-e"
    write_boundary_e(target)
    payload = json.loads((target / "readiness_revocation.json").read_text())
    payload["k1_approved"] = True
    (target / "readiness_revocation.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    hashes = json.loads((target / "boundary_e_hashes.json").read_text())
    import hashlib

    hashes["artifacts"]["readiness_revocation.json"] = hashlib.sha256(
        (target / "readiness_revocation.json").read_bytes()
    ).hexdigest()
    (target / "boundary_e_hashes.json").write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        verify_boundary_e(target)


def test_boundary_e_does_not_modify_historical_k0t(tmp_path: Path) -> None:
    source = Path("data/q5_frontier/dev-k0t-audit")
    before = {item.name: item.read_bytes() for item in source.iterdir() if item.is_file()}
    write_boundary_e(tmp_path / "boundary-e")
    after = {item.name: item.read_bytes() for item in source.iterdir() if item.is_file()}
    assert before == after
