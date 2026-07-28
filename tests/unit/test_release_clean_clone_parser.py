from __future__ import annotations

import sys

import pytest

from scripts import verify_release_clean_clone
from scripts.verify_release_clean_clone import _last_json_object, _resolve_command


def test_last_json_object_allows_trailing_diagnostics() -> None:
    output = 'prefix\n{"claim_count": 14, "nested": {"value": 7}}\nwarning: cached runtime\n'

    assert _last_json_object(output) == {
        "claim_count": 14,
        "nested": {"value": 7},
    }


def test_last_json_object_selects_latest_complete_top_level_object() -> None:
    output = '{"older": true}\nstatus\n{"newer": {"value": 2}}\ntrailer'

    assert _last_json_object(output) == {"newer": {"value": 2}}


def test_last_json_object_rejects_output_without_complete_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        _last_json_object('warning only\n{"incomplete": true')


def test_resolve_command_falls_back_to_python_uv_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verify_release_clean_clone.shutil, "which", lambda _: None)
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(
        verify_release_clean_clone.importlib.util,
        "find_spec",
        lambda name: object() if name == "uv" else None,
    )

    command, launcher = _resolve_command(["uv", "sync", "--locked"])

    assert command == [sys.executable, "-m", "uv", "sync", "--locked"]
    assert launcher == "python-module-uv"
