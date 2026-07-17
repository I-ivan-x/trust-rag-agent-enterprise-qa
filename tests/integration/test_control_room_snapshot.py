from __future__ import annotations

import json

import pytest

from app.eval import control_room_snapshot
from app.schemas.control_room import ControlRoomSnapshot


def test_control_room_snapshot_is_current_runtime_only_and_provenanced() -> None:
    result = control_room_snapshot.build_control_room_snapshot(check=True)
    assert result["scenario_count"] == 2
    assert result["model_requests"] == 0
    assert result["external_requests"] == 0

    raw = control_room_snapshot.OUTPUT_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    snapshot = ControlRoomSnapshot.model_validate(payload)
    assert snapshot.provenance.mode == "real"
    assert {row.scenario_id for row in snapshot.scenarios} == {
        "approval_path",
        "blocked_path",
    }
    assert all(token not in raw.lower() for token in ("gold", "expected_action", "correct"))


def test_control_room_snapshot_source_and_output_mutations_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    source = tmp_path / "source.json"
    source_payload = json.loads(control_room_snapshot.SOURCE_PATH.read_text(encoding="utf-8"))
    source_payload[0]["query"] = "mutated runtime query"
    source.write_text(json.dumps(source_payload), encoding="utf-8")
    monkeypatch.setattr(control_room_snapshot, "SOURCE_PATH", source)
    monkeypatch.setattr(
        control_room_snapshot,
        "_git_blob",
        lambda _commit, _path: control_room_snapshot.SOURCE_PATH.read_bytes(),
    )
    with pytest.raises(ValueError, match="source hash mismatch"):
        control_room_snapshot.build_control_room_snapshot(check=True)

    monkeypatch.undo()
    output = tmp_path / "snapshot.json"
    output.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(control_room_snapshot, "OUTPUT_PATH", output)
    with pytest.raises(ValueError, match="snapshot drifted"):
        control_room_snapshot.build_control_room_snapshot(check=True)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("scenarios", 0, "unexpected"), "field"),
        (("scenarios", 1, "terminal", "executed_side_effect"), True),
        (("scenarios", 1, "proposal", "action"), "send_alert"),
    ],
)
def test_control_room_schema_mutations_fail_closed(path, value) -> None:
    payload = json.loads(control_room_snapshot.OUTPUT_PATH.read_text(encoding="utf-8"))
    target = payload
    for token in path[:-1]:
        target = target[token]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        ControlRoomSnapshot.model_validate(payload)
