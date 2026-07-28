"""Physically separated Q5 runtime and grader dataset loaders."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.q5_task import (
    Q5_TOOL_WHITELIST,
    Q5EnvironmentState,
    Q5Gold,
    Q5TaskInput,
)


@dataclass(frozen=True)
class Q5EnvironmentStore(Mapping[str, Q5EnvironmentState]):
    """Read-only environment mapping keyed by ``environment_ref``."""

    _states: Mapping[str, Q5EnvironmentState]

    @classmethod
    def from_states(cls, states: Iterable[Q5EnvironmentState]) -> Q5EnvironmentStore:
        by_ref: dict[str, Q5EnvironmentState] = {}
        for state in states:
            if state.environment_ref in by_ref:
                raise ValueError(f"duplicate Q5 environment_ref: {state.environment_ref}")
            by_ref[state.environment_ref] = state
        return cls(MappingProxyType(by_ref))

    def __getitem__(self, key: str) -> Q5EnvironmentState:
        return self._states[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._states)

    def __len__(self) -> int:
        return len(self._states)


@dataclass(frozen=True)
class Q5RuntimeDataset:
    """Runtime bundle deliberately containing no gold object or gold path."""

    tasks: tuple[Q5TaskInput, ...]
    environment: Q5EnvironmentStore


class Q5DatasetValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    task_count: int = Field(ge=0)
    environment_count: int = Field(ge=0)
    gold_count: int | None = Field(default=None, ge=0)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def load_q5_tasks(path: Path | str) -> list[Q5TaskInput]:
    tasks = [Q5TaskInput.model_validate(record) for record in _read_jsonl(Path(path))]
    _require_unique_ids((task.case_id for task in tasks), label="Q5 case_id")
    return tasks


def load_q5_environment(path: Path | str) -> Q5EnvironmentStore:
    states = [
        Q5EnvironmentState.model_validate(record) for record in _read_jsonl(Path(path))
    ]
    return Q5EnvironmentStore.from_states(states)


def load_q5_gold(path: Path | str) -> dict[str, Q5Gold]:
    gold_rows = [Q5Gold.model_validate(record) for record in _read_jsonl(Path(path))]
    _require_unique_ids((row.case_id for row in gold_rows), label="Q5 gold case_id")
    return {row.case_id: row for row in gold_rows}


def load_q5_runtime_dataset(
    tasks_path: Path | str,
    environment_path: Path | str,
) -> Q5RuntimeDataset:
    """Load runtime inputs only. The signature intentionally has no gold parameter."""

    tasks = load_q5_tasks(tasks_path)
    environment = load_q5_environment(environment_path)
    report = validate_q5_dataset(tasks, environment)
    if not report.valid:
        raise ValueError("invalid Q5 runtime dataset: " + "; ".join(report.errors))
    return Q5RuntimeDataset(tasks=tuple(tasks), environment=environment)


def join_q5_results_with_gold(
    results: Iterable[Mapping[str, Any] | BaseModel],
    gold: Mapping[str, Q5Gold],
) -> list[dict[str, Any]]:
    """Join completed runtime results with gold in the grader-only stage."""

    grader_rows: list[dict[str, Any]] = []
    for result in results:
        payload = _result_payload(result)
        case_id = payload.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("every Q5 result must contain a non-empty case_id")
        if case_id not in gold:
            raise KeyError(f"missing Q5 gold for result case_id: {case_id}")
        grader_rows.append(
            {
                "result": payload,
                "gold": gold[case_id].model_dump(mode="json"),
            }
        )
    return grader_rows


def validate_q5_dataset(
    tasks: Iterable[Q5TaskInput],
    environment: Q5EnvironmentStore,
    gold: Mapping[str, Q5Gold] | None = None,
) -> Q5DatasetValidationReport:
    task_rows = list(tasks)
    errors: list[str] = []
    warnings: list[str] = []

    task_ids = [task.case_id for task in task_rows]
    duplicates = _duplicates(task_ids)
    if duplicates:
        errors.append("duplicate task case_id values: " + ", ".join(duplicates))

    missing_environment = sorted(
        {
            task.environment_ref
            for task in task_rows
            if task.environment_ref not in environment
        }
    )
    if missing_environment:
        errors.append("missing environment_ref values: " + ", ".join(missing_environment))

    invalid_tools = sorted(
        {
            str(tool)
            for task in task_rows
            for tool in task.available_tools
            if str(tool) not in Q5_TOOL_WHITELIST
        }
    )
    if invalid_tools:
        errors.append("tools outside Q5 whitelist: " + ", ".join(invalid_tools))

    partitions = {
        partition
        for task in task_rows
        if (partition := _namespace_partition(task.corpus_namespace)) is not None
    }
    if len(partitions) > 1:
        errors.append("q5_dev and q5_test corpus namespaces must not be mixed")

    task_id_set = set(task_ids)
    if gold is not None:
        gold_ids = set(gold)
        missing_gold = sorted(task_id_set - gold_ids)
        extra_gold = sorted(gold_ids - task_id_set)
        if missing_gold:
            errors.append("missing gold case_id values: " + ", ".join(missing_gold))
        if extra_gold:
            errors.append("gold has unknown case_id values: " + ", ".join(extra_gold))

    unused_environment = sorted(set(environment) - {task.environment_ref for task in task_rows})
    if unused_environment:
        warnings.append("unused environment_ref values: " + ", ".join(unused_environment))

    return Q5DatasetValidationReport(
        valid=not errors,
        task_count=len(task_rows),
        environment_count=len(environment),
        gold_count=len(gold) if gold is not None else None,
        errors=errors,
        warnings=warnings,
    )


def build_q5_dataset_manifest(
    *,
    tasks_path: Path | str,
    environment_path: Path | str,
    gold_path: Path | str,
    corpus_path: Path | str,
) -> dict[str, Any]:
    paths = {
        "tasks": Path(tasks_path),
        "environment": Path(environment_path),
        "gold": Path(gold_path),
        "corpus": Path(corpus_path),
    }
    return {
        "schema_version": "q5-dataset-manifest-v1",
        "paths": {name: path.as_posix() for name, path in paths.items()},
        "sha256": {name: _sha256_path(path) for name, path in paths.items()},
    }


def write_q5_dataset_manifest(path: Path | str, manifest: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(dict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Q5 JSONL file not found: {path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at {path}:{line_number}: {exc.msg}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"Q5 JSONL row must be an object at {path}:{line_number}")
        records.append(record)
    return records


def _require_unique_ids(values: Iterable[str], *, label: str) -> None:
    duplicates = _duplicates(values)
    if duplicates:
        raise ValueError(f"duplicate {label} values: " + ", ".join(duplicates))


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _namespace_partition(namespace: str) -> str | None:
    normalized = namespace.lower().replace("-", "_")
    if normalized.startswith("q5_dev"):
        return "dev"
    if normalized.startswith("q5_test"):
        return "test"
    return None


def _result_payload(result: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, Mapping):
        return dict(result)
    raise TypeError("Q5 results must be mappings or Pydantic models")


def _sha256_path(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        raise FileNotFoundError(f"Q5 manifest artifact not found: {path}")

    digest = hashlib.sha256()
    files = sorted(candidate for candidate in path.rglob("*") if candidate.is_file())
    for file_path in files:
        relative = file_path.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
