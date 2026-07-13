from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_provenance import verify_q5_graded_run
from app.eval.q5_runner import grade_q5_run
from tests.integration.test_q5_harness import _single_case_graded_run

V1_FIXTURE_ROOT = Path("tests/fixtures/q5_protocol_v1")
_V1_EMPTY_ARTIFACTS = {"otel_spans.jsonl", "tool_events.jsonl"}
V2_FIXTURE_ROOT = Path("tests/fixtures/q5_protocol_v2")
_V2_EMPTY_ARTIFACTS = {"otel_spans.jsonl", "tool_events.jsonl"}


def test_q5_committed_v1_artifact_fixture_is_verifiable(tmp_path: Path) -> None:
    run_dir, gold_path = _materialize_v1_fixture(tmp_path)

    verified = verify_q5_graded_run(run_dir, gold_path)

    assert verified.protocol_version == "v1"
    assert verified.run_id == "q5-v1-compact"
    assert verified.mock_used is True
    assert verified.real_run is False


def test_q5_committed_v2_artifact_fixture_is_verifiable(tmp_path: Path) -> None:
    run_dir, gold_path = _materialize_v2_fixture(tmp_path)

    verified = verify_q5_graded_run(run_dir, gold_path)

    assert verified.protocol_version == "v2"
    assert verified.run_id == "q5-v2-compact"
    assert verified.mock_used is True
    assert verified.real_run is False


def test_q5_new_v4_artifact_is_verifiable(tmp_path: Path) -> None:
    graded, gold_path = _single_case_graded_run(
        tmp_path,
        run_id="q5-v3-versioned",
        role="primary",
        model=Q5DeterministicMockPolicyModel(),
    )

    verified = verify_q5_graded_run(graded.run_dir, gold_path)
    raw_manifest = _json(graded.run_dir / "manifest.json")
    graded_manifest = _json(graded.run_dir / "graded_manifest.json")
    summary = _json(graded.run_dir / "summary.json")
    gates = _json(graded.run_dir / "gates.json")

    assert verified.protocol_version == "v4"
    assert raw_manifest["schema_version"] == "q5-run-manifest-v4"
    assert raw_manifest["prompt"]["version"] == "q5-structured-policy-v4"
    assert graded_manifest["schema_version"] == "q5-graded-manifest-v4"
    assert summary["schema_version"] == "q5-metrics-v4"
    assert gates["schema_version"] == "q5-gates-v4"


def test_q5_v1_artifacts_are_verification_only_for_current_grader(
    tmp_path: Path,
) -> None:
    run_dir, gold_path = _materialize_v1_fixture(tmp_path)
    before = _file_hashes(run_dir)

    with pytest.raises(ValueError, match="verification-only"):
        grade_q5_run(run_dir, gold_path)

    assert _file_hashes(run_dir) == before


@pytest.mark.parametrize("raw_protocol", ["v1", "v3"])
def test_q5_cross_protocol_graded_recompute_is_rejected(
    tmp_path: Path,
    raw_protocol: str,
) -> None:
    if raw_protocol == "v1":
        run_dir, gold_path = _materialize_v1_fixture(tmp_path)
        replacement = "q5-graded-manifest-v2"
    else:
        graded, gold_path = _single_case_graded_run(
            tmp_path,
        run_id="q5-v3-cross-protocol",
            role="primary",
            model=Q5DeterministicMockPolicyModel(),
        )
        run_dir = graded.run_dir
        replacement = "q5-graded-manifest-v1"
    manifest_path = run_dir / "graded_manifest.json"
    manifest = _json(manifest_path)
    manifest["schema_version"] = replacement
    _write_json(manifest_path, manifest)
    _refresh_graded_hash(run_dir, manifest_path.name)

    with pytest.raises(ValueError, match="artifact protocol mismatch"):
        verify_q5_graded_run(run_dir, gold_path)


@pytest.mark.parametrize(
    ("artifact", "replacement"),
    [
        ("summary.json", "q5-metrics-v2"),
        ("gates.json", "q5-gates-v2"),
    ],
)
def test_q5_v1_mixed_metric_or_gate_schema_is_rejected(
    tmp_path: Path,
    artifact: str,
    replacement: str,
) -> None:
    run_dir, gold_path = _materialize_v1_fixture(tmp_path)
    path = run_dir / artifact
    payload = _json(path)
    payload["schema_version"] = replacement
    _write_json(path, payload)
    _refresh_graded_hash(run_dir, artifact)

    with pytest.raises(ValueError, match="artifact protocol mismatch"):
        verify_q5_graded_run(run_dir, gold_path)


def _materialize_v1_fixture(tmp_path: Path) -> tuple[Path, Path]:
    run_dir = tmp_path / "q5-v1-compact"
    run_dir.mkdir()
    for source in V1_FIXTURE_ROOT.iterdir():
        if source.name in {"gold.jsonl", "README.md"}:
            continue
        (run_dir / source.name).write_bytes(_legacy_fixture_bytes(source))
    for filename in _V1_EMPTY_ARTIFACTS:
        (run_dir / filename).write_bytes(b"")
    gold_path = tmp_path / "q5-v1-compact-gold.jsonl"
    gold_path.write_bytes(_legacy_fixture_bytes(V1_FIXTURE_ROOT / "gold.jsonl"))
    return run_dir, gold_path


def _materialize_v2_fixture(tmp_path: Path) -> tuple[Path, Path]:
    run_dir = tmp_path / "q5-v2-compact"
    run_dir.mkdir()
    for source in V2_FIXTURE_ROOT.iterdir():
        if source.name in {"gold.jsonl", "README.md"}:
            continue
        (run_dir / source.name).write_bytes(_legacy_fixture_bytes(source))
    for filename in _V2_EMPTY_ARTIFACTS:
        (run_dir / filename).write_bytes(b"")
    gold_path = tmp_path / "q5-v2-compact-gold.jsonl"
    gold_path.write_bytes(_legacy_fixture_bytes(V2_FIXTURE_ROOT / "gold.jsonl"))
    return run_dir, gold_path


def _legacy_fixture_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise AssertionError(f"invalid normalized v1 fixture source: {path}")
    return text.replace("\n", "\r\n").encode("utf-8")


def _refresh_graded_hash(run_dir: Path, filename: str) -> None:
    hashes_path = run_dir / "graded_hashes.json"
    hashes = _json(hashes_path)
    hashes["artifacts"][filename] = hashlib.sha256(
        (run_dir / filename).read_bytes()
    ).hexdigest()
    _write_json(hashes_path, hashes)


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.iterdir()
    }


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
