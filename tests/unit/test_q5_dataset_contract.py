from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.eval.q5_dataset import (
    build_q5_dataset_manifest,
    join_q5_results_with_gold,
    load_q5_environment,
    load_q5_gold,
    load_q5_runtime_dataset,
    load_q5_tasks,
    validate_q5_dataset,
    write_q5_dataset_manifest,
)
from app.schemas.q5_task import Q5_GOLD_ONLY_FIELDS, Q5Gold, Q5TaskInput

FIXTURE_ROOT = Path("tests/fixtures/q5")
TASKS_PATH = FIXTURE_ROOT / "tasks.jsonl"
ENVIRONMENT_PATH = FIXTURE_ROOT / "environment.jsonl"
GOLD_PATH = FIXTURE_ROOT / "gold.jsonl"
CORPUS_PATH = FIXTURE_ROOT / "corpus"


def _task_payload() -> dict:
    return json.loads(TASKS_PATH.read_text(encoding="utf-8").strip())


def test_q5_runtime_loader_has_no_gold_parameter() -> None:
    parameters = inspect.signature(load_q5_runtime_dataset).parameters
    assert tuple(parameters) == ("tasks_path", "environment_path")

    runtime = load_q5_runtime_dataset(TASKS_PATH, ENVIRONMENT_PATH)
    assert len(runtime.tasks) == 1
    assert not hasattr(runtime, "gold")


def test_q5_task_rejects_gold_only_fields() -> None:
    clean = _task_payload()
    for field in Q5_GOLD_ONLY_FIELDS:
        payload = {**clean, field: "grader-only-canary"}
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            Q5TaskInput.model_validate(payload)


def test_q5_gold_join_happens_after_results() -> None:
    runtime = load_q5_runtime_dataset(TASKS_PATH, ENVIRONMENT_PATH)
    runtime_result = {
        "case_id": runtime.tasks[0].case_id,
        "system_name": "q5_fixture_rule",
        "trajectory_complete": True,
    }
    assert not (set(runtime_result) & Q5_GOLD_ONLY_FIELDS)

    gold = load_q5_gold(GOLD_PATH)
    rows = join_q5_results_with_gold([runtime_result], gold)

    assert rows[0]["result"] == runtime_result
    assert rows[0]["gold"]["stratum"] == "semantic"
    assert "stratum" not in rows[0]["result"]


def test_q5_case_ids_and_environment_refs_validate(tmp_path: Path) -> None:
    tasks = load_q5_tasks(TASKS_PATH)
    environment = load_q5_environment(ENVIRONMENT_PATH)
    gold = load_q5_gold(GOLD_PATH)
    assert validate_q5_dataset(tasks, environment, gold).valid is True

    missing_environment = tasks[0].model_copy(update={"environment_ref": "missing-env"})
    report = validate_q5_dataset([missing_environment], environment, gold)
    assert report.valid is False
    assert any("missing environment_ref" in error for error in report.errors)

    duplicate_tasks_path = tmp_path / "duplicate-tasks.jsonl"
    row = TASKS_PATH.read_text(encoding="utf-8").strip()
    duplicate_tasks_path.write_text(f"{row}\n{row}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate Q5 case_id"):
        load_q5_tasks(duplicate_tasks_path)

    duplicate_environment_path = tmp_path / "duplicate-environment.jsonl"
    environment_row = ENVIRONMENT_PATH.read_text(encoding="utf-8").strip()
    duplicate_environment_path.write_text(
        f"{environment_row}\n{environment_row}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate Q5 environment_ref"):
        load_q5_environment(duplicate_environment_path)

    duplicate_gold_path = tmp_path / "duplicate-gold.jsonl"
    gold_row = GOLD_PATH.read_text(encoding="utf-8").strip()
    duplicate_gold_path.write_text(f"{gold_row}\n{gold_row}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate Q5 gold case_id"):
        load_q5_gold(duplicate_gold_path)


def test_q5_manifest_hashes_task_gold_env_corpus_separately(tmp_path: Path) -> None:
    manifest = build_q5_dataset_manifest(
        tasks_path=TASKS_PATH,
        environment_path=ENVIRONMENT_PATH,
        gold_path=GOLD_PATH,
        corpus_path=CORPUS_PATH,
    )
    hashes = manifest["sha256"]

    assert set(hashes) == {"tasks", "environment", "gold", "corpus"}
    assert all(len(value) == 64 for value in hashes.values())
    assert len(set(hashes.values())) == 4

    output = write_q5_dataset_manifest(tmp_path / "manifest.json", manifest)
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["sha256"] == hashes
    assert persisted["paths"]["gold"].endswith("gold.jsonl")


def test_q5_requested_capability_never_falls_back_to_gold() -> None:
    payload = _task_payload()
    payload.pop("requested_capability")
    payload["gold_action"] = "send_alert"

    with pytest.raises(ValidationError) as exc_info:
        Q5TaskInput.model_validate(payload)

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("requested_capability",) for error in errors)
    assert any(error["loc"] == ("gold_action",) for error in errors)


def test_q5_tool_allowlist_and_namespace_isolation() -> None:
    payload = _task_payload()
    payload["available_tools"] = ["shell_exec"]
    with pytest.raises(ValidationError):
        Q5TaskInput.model_validate(payload)

    dev_task = Q5TaskInput.model_validate(_task_payload())
    test_task = dev_task.model_copy(
        update={"case_id": "q5-fixture-002", "corpus_namespace": "q5_test_fixture"}
    )
    environment = load_q5_environment(ENVIRONMENT_PATH)
    report = validate_q5_dataset([dev_task, test_task], environment)
    assert report.valid is False
    assert "q5_dev and q5_test corpus namespaces must not be mixed" in report.errors


def test_q5_gold_action_sets_must_be_disjoint() -> None:
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8").strip())
    payload["forbidden_terminal_actions"] = ["escalate_to_human"]
    with pytest.raises(ValidationError, match="overlap"):
        Q5Gold.model_validate(payload)
