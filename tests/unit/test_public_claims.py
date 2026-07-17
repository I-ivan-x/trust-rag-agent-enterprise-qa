from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.eval import public_claims
from app.eval.public_claims import load_and_verify_registry, render_public_claims


def test_registry_is_strict_complete_and_generates_all_public_views() -> None:
    registry = load_and_verify_registry()
    assert len(registry.claims) == 14
    assert {claim.question_id for claim in registry.claims} == {"Q1", "Q2", "Q3", "Q4", "Q5"}
    assert registry.q5_overall_status == "scoped_negative_complete"
    rendered = render_public_claims(registry)
    assert set(rendered) == set(public_claims.GENERATED_PATHS)
    for payload in rendered.values():
        assert b"uncovered 32/32" not in payload


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_status",
        "unknown_evidence_mode",
        "duplicate_claim_id",
        "missing_numerator",
        "source_hash",
        "source_run_id",
        "source_commit",
        "ambiguous_wording",
    ],
)
def test_registry_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    payload = json.loads(public_claims.REGISTRY_PATH.read_text(encoding="utf-8"))
    if mutation == "unknown_status":
        payload["claims"][0]["status"] = "proven"
    elif mutation == "unknown_evidence_mode":
        payload["claims"][0]["evidence_mode"] = "anecdotal"
    elif mutation == "duplicate_claim_id":
        payload["claims"][1]["claim_id"] = payload["claims"][0]["claim_id"]
    elif mutation == "missing_numerator":
        del payload["claims"][0]["metrics"]["false_answer_rate"]["numerator"]
    elif mutation == "source_hash":
        payload["claims"][0]["source_artifacts"][0]["sha256"] = "0" * 64
    elif mutation == "source_run_id":
        payload["claims"][0]["source_artifacts"][0]["run_id"] = "forged-run"
    elif mutation == "source_commit":
        payload["claims"][0]["source_artifacts"][0]["evidence_commit"] = "0" * 40
    else:
        payload["claims"][0]["public_summary"] += " uncovered 32/32"
    target = tmp_path / "registry.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    original_tracked = public_claims._is_git_tracked
    monkeypatch.setattr(
        public_claims,
        "_is_git_tracked",
        lambda path: True if Path(path) == target else original_tracked(path),
    )
    expected_error = (ValidationError, ValueError)
    with pytest.raises(expected_error):
        load_and_verify_registry(target)


def test_untracked_source_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(public_claims.REGISTRY_PATH.read_text(encoding="utf-8"))
    source_path = payload["claims"][0]["source_artifacts"][0]["path"]
    target = tmp_path / "registry.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    original_tracked = public_claims._is_git_tracked
    monkeypatch.setattr(
        public_claims,
        "_is_git_tracked",
        lambda path: (
            True
            if Path(path) == target
            else False
            if path == source_path
            else original_tracked(path)
        ),
    )
    with pytest.raises(ValueError, match="not Git tracked"):
        load_and_verify_registry(target)


def test_check_mode_detects_drift_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "generated.json"
    target.write_bytes(b"drift\n")
    before = target.read_bytes()
    registry = load_and_verify_registry()
    monkeypatch.setattr(public_claims, "load_and_verify_registry", lambda: registry)
    monkeypatch.setattr(public_claims, "GENERATED_PATHS", (target,))
    monkeypatch.setattr(public_claims, "render_public_claims", lambda _: {target: b"expected\n"})
    with pytest.raises(ValueError, match="drifted"):
        public_claims.build_public_claims(check=True)
    assert target.read_bytes() == before


def test_not_evaluated_claim_cannot_self_report_metrics() -> None:
    registry = load_and_verify_registry()
    claim = next(item for item in registry.claims if item.claim_id == "q5.open_world_llm_value")
    payload = copy.deepcopy(claim.model_dump(mode="json"))
    payload["metrics"] = {
        "invented": {"numerator": 1, "denominator": 1, "value": 1, "unit": "rate"}
    }
    with pytest.raises(ValidationError):
        type(claim).model_validate(payload)
