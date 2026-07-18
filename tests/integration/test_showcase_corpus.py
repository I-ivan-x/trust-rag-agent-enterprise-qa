from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval.showcase_corpus import (
    SHOWCASE_ROOT,
    build_interview_showcase,
    verify_interview_showcase,
    verify_showcase_isolation,
)


def test_showcase_is_hash_closed_generated_and_formally_isolated() -> None:
    receipt = verify_interview_showcase()
    assert receipt["file_count"] == 12
    assert receipt["data_mode"] == "synthetic"
    assert receipt["use"] == "demonstration_only"
    assert receipt["headline_eligible"] is False
    assert receipt["formal_evaluation"] is False
    assert receipt["model_requests"] == receipt["external_requests"] == 0
    assert receipt["formal_claim_references"] == 0
    assert build_interview_showcase(check=True)["status"] == "passed"


def test_showcase_hash_mutation_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "interview-v1"
    target.mkdir()
    for source in SHOWCASE_ROOT.iterdir():
        if source.is_file():
            (target / source.name).write_bytes(source.read_bytes())
    (target / "current-runbook.md").write_text("forged", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_interview_showcase(target, verify_formal_isolation=False)


def test_showcase_extra_file_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "interview-v1"
    target.mkdir()
    for source in SHOWCASE_ROOT.iterdir():
        if source.is_file():
            (target / source.name).write_bytes(source.read_bytes())
    (target / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="file matrix"):
        verify_interview_showcase(target, verify_formal_isolation=False)


def test_formal_claim_surface_cannot_reference_showcase(tmp_path: Path) -> None:
    formal = tmp_path / "headline.json"
    formal.write_text(
        json.dumps({"source_artifacts": [{"path": "data/showcase/interview-v1/manifest.json"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="references showcase"):
        verify_showcase_isolation((formal,))
