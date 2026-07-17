"""Build and verify the public runtime-only control-room snapshot."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from app.schemas.control_room import ControlRoomSnapshot

SOURCE_PATH = Path("frontend/src/data/trajectories.json")
OUTPUT_PATH = Path("frontend/src/data/control-room-trajectory.json")
SOURCE_SHA256 = "c4dacec66b41001360fe2d6f02e624276a24ac3a389d0f7022ad9b2168f5c7dc"
RUN_ID = "q4-p5-selection-calibrated"
EXECUTION_COMMIT = "39d6cb78e6fcab4ed95d951d8c16f9925e048d77"
ARTIFACT_COMMIT = "080f56a64d781e3c253a64a2c53ee4b62b339bad"
SCENARIOS = (("approval_path", "ora-t05"), ("blocked_path", "ora-t15"))


def build_control_room_snapshot(*, check: bool = False) -> dict[str, Any]:
    source_bytes = _git_blob(ARTIFACT_COMMIT, SOURCE_PATH.as_posix())
    if source_bytes is None or hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA256:
        raise ValueError("control-room source hash mismatch")
    if _git_type(EXECUTION_COMMIT) != "commit" or not _is_ancestor(EXECUTION_COMMIT):
        raise ValueError("control-room execution commit is not a current ancestor")

    source_rows = json.loads(source_bytes)
    working_rows = json.loads(SOURCE_PATH.read_bytes())
    if working_rows != source_rows:
        raise ValueError("control-room working source differs from the artifact commit")
    if not isinstance(source_rows, list):
        raise ValueError("control-room source must be a JSON array")
    by_ref = {row.get("case_id"): row for row in source_rows if isinstance(row, dict)}
    if len(by_ref) != len(source_rows):
        raise ValueError("control-room source refs are missing or duplicated")

    scenarios = [
        _runtime_scenario(scenario_id, source_ref, by_ref[source_ref])
        for scenario_id, source_ref in SCENARIOS
    ]
    payload = ControlRoomSnapshot.model_validate(
        {
            "schema_version": "control-room-trajectory-v1",
            "provenance": {
                "source_path": SOURCE_PATH.as_posix(),
                "source_sha256": SOURCE_SHA256,
                "run_id": RUN_ID,
                "execution_commit": EXECUTION_COMMIT,
                "artifact_commit": ARTIFACT_COMMIT,
                "mode": "real",
            },
            "scenarios": scenarios,
        }
    ).model_dump(mode="json")
    expected = _json_bytes(payload)

    if check:
        if not OUTPUT_PATH.is_file() or OUTPUT_PATH.read_bytes() != expected:
            raise ValueError("control-room snapshot drifted")
    else:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_bytes(expected)

    return {
        "scenario_count": len(scenarios),
        "source_sha256": SOURCE_SHA256,
        "snapshot_sha256": hashlib.sha256(expected).hexdigest(),
        "model_requests": 0,
        "external_requests": 0,
    }


def _runtime_scenario(scenario_id: str, source_ref: str, row: dict[str, Any]) -> dict[str, Any]:
    required = {"query", "user_role", "authorized", "read", "detect", "act", "govern"}
    if not required <= row.keys():
        raise ValueError(f"control-room source row is incomplete: {source_ref}")
    return {
        "scenario_id": scenario_id,
        "source_ref": source_ref,
        "query": row["query"],
        "actor_role": row["user_role"],
        "authorized": row["authorized"],
        "observation": {
            "retrieved": row["read"]["retrieved"],
            "surviving": row["read"]["surviving"],
            "blocked": row["read"]["blocked"],
            "citations": row["read"]["citations"],
        },
        "evidence": {
            "conditions": row["detect"]["conditions"],
            "authorized_actor": row["detect"]["authorized_actor"],
            "evidence_decision": row["detect"]["evidence_decision"],
        },
        "proposal": {
            "action": row["act"]["proposed_action"],
            "controller_source": row["act"]["controller_source"],
            "risk_tier": row["act"]["risk_tier"],
        },
        "policy": {
            "validator_ok": row["govern"]["validator_ok"],
            "forced_action": row["govern"]["forced_action"],
        },
        "terminal": {
            "approval_state": row["govern"]["approval_state"],
            "executed_side_effect": row["govern"]["executed_side_effect"],
            "sink_record_id": row["govern"]["sink_record_id"],
        },
    }


def _git_blob(commit: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{path}"], capture_output=True
    )
    return result.stdout if result.returncode == 0 else None


def _git_type(oid: str) -> str | None:
    result = subprocess.run(["git", "cat-file", "-t", oid], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def _is_ancestor(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            capture_output=True,
        ).returncode
        == 0
    )


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
