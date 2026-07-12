"""Read-only, sealed-artifact replay diagnostics for Q5 graded runs."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.eval.q5_dataset import load_q5_gold
from app.eval.q5_provenance import (
    q5_read_jsonl,
    q5_sha256_file,
    verify_q5_graded_run,
)
from app.govern.q5_tool_validator import q5_completed_observation_key
from app.schemas.q5_task import Q5ObservationTool

_LLM = "q5_llm_agent"
_HYBRID = "q5_hybrid_agent"
_SEMANTIC_SYSTEMS = (_LLM, _HYBRID)


def replay_q5_graded_run(
    run_dir: Path | str,
    gold_path: Path | str,
    output_dir: Path | str,
    *,
    fixed_table_solvability: float | None = None,
    require_batch5d_signature: bool = False,
) -> dict[str, Any]:
    """Verify first, then derive diagnostics without mutating the source run."""

    root = Path(run_dir).resolve()
    gold_source = Path(gold_path).resolve()
    target = Path(output_dir).resolve()
    if "q5_test" in root.as_posix().lower() or "q5_test" in gold_source.as_posix().lower():
        raise ValueError("Q5 replay diagnostic refuses q5_test inputs")
    if target == root or root in target.parents:
        raise ValueError("Q5 replay output must be independent of the source run")
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Q5 replay output directory is not empty: {target}")

    source_hashes_before = _directory_hashes(root)
    verified = verify_q5_graded_run(root, gold_source)
    results = q5_read_jsonl(root / "results.jsonl")
    graded = q5_read_jsonl(root / "graded_rows.jsonl")
    tools = q5_read_jsonl(root / "tool_events.jsonl")
    trajectory_events = q5_read_jsonl(root / "trajectory.jsonl")
    gold = load_q5_gold(gold_source)

    tool_by_trial: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for event in tools:
        tool_by_trial[_trial_tuple(event)].append(event)
    trajectory_by_trial: dict[
        tuple[str, str, int], list[dict[str, Any]]
    ] = defaultdict(list)
    for event in trajectory_events:
        trajectory_by_trial[_trial_tuple(event)].append(event)
    graded_by_trial = {_trial_tuple(row): row for row in graded}
    trajectories: list[dict[str, Any]] = []
    duplicate_total = 0
    for result in results:
        key = _trial_tuple(result)
        completed: set[str] = set()
        completed_tool_names: set[str] = set()
        duplicate_keys: list[str] = []
        sequence: list[dict[str, Any]] = []
        for event in sorted(
            tool_by_trial.get(key, []),
            key=lambda item: str(item.get("request_id") or ""),
        ):
            canonical = q5_completed_observation_key(
                Q5ObservationTool(str(event["tool_name"])),
                dict(event["request_args"]),
            )
            is_duplicate = canonical in completed
            if is_duplicate:
                duplicate_keys.append(canonical)
                duplicate_total += 1
            if event.get("status") in {"ok", "not_found"}:
                completed.add(canonical)
                completed_tool_names.add(str(event["tool_name"]))
            sequence.append(
                {
                    "tool": event["tool_name"],
                    "canonical_args": canonical.split("|", 1)[1],
                    "status": event["status"],
                    "duplicate_after_success": is_duplicate,
                }
            )
        grade = graded_by_trial[key]
        ordered_events = sorted(
            trajectory_by_trial[key],
            key=lambda item: (int(item["step_index"]), item["event_type"] == "terminal"),
        )
        required = set(grade["required_observations"])
        completed_required_steps = [
            int(event["step_index"])
            for event in ordered_events
            if event.get("event_type") == "observation"
            and event.get("tool_status") in {"ok", "not_found"}
            and event.get("tool") in required
        ]
        terminal_steps = [
            int(event["step_index"])
            for event in ordered_events
            if event.get("event_type") == "terminal"
        ]
        post_observation_terminal = (
            terminal_steps[0] == max(completed_required_steps) + 1
            if required <= completed_tool_names
            and required
            and completed_required_steps
            and len(terminal_steps) == 1
            else None
        )
        trajectories.append(
            {
                "case_id": key[0],
                "system": key[1],
                "run_index": key[2],
                "stratum": grade["stratum"],
                "route": result["route"],
                "observations": sequence,
                "duplicate_successful_calls": duplicate_keys,
                "terminal_action": result["final_action"],
                "task_success": grade["task_success"],
                "trajectory_qualified_success": grade[
                    "trajectory_qualified_success"
                ],
                "llm_calls": result["llm_calls"],
                "total_tokens": result["total_tokens"],
                "post_observation_terminal": post_observation_terminal,
            }
        )

    by_stratum = _stratum_usage(trajectories)
    semantic_calls = {
        system: sum(
            row["llm_calls"]
            for row in trajectories
            if row["system"] == system and row["stratum"] == "semantic"
        )
        for system in _SEMANTIC_SYSTEMS
    }
    three_call = {
        system: sum(
            row["llm_calls"] == 3
            for row in trajectories
            if row["system"] == system
        )
        for system in _SEMANTIC_SYSTEMS
    }
    stable_failures = sorted(
        case_id
        for case_id in gold
        if gold[case_id].stratum.value == "semantic"
        and all(
            all(
                not row["trajectory_qualified_success"]
                for row in trajectories
                if row["case_id"] == case_id and row["system"] == system
            )
            for system in _SEMANTIC_SYSTEMS
        )
    )
    calls_upper = {
        system: sum(
            row["route"] == "llm"
            for row in trajectories
            if row["system"] == system
        )
        + sum(
            any(obs["status"] in {"ok", "not_found"} for obs in row["observations"])
            for row in trajectories
            if row["system"] == system
        )
        for system in _SEMANTIC_SYSTEMS
    }
    call_ratio = round(calls_upper[_HYBRID] / calls_upper[_LLM], 6)
    invariance = _counterfactual_invariance(trajectories, gold)
    adaptation_values = [not row["decision_invariant"] for row in invariance]
    terminal_rates = {
        system: _optional_boolean_rate(
            row["post_observation_terminal"]
            for row in trajectories
            if row["system"] == system
        )
        for system in _SEMANTIC_SYSTEMS
    }
    report = {
        "schema_version": "q5-real-artifact-replay-v1",
        "source": {
            "run_id": verified.run_id,
            "protocol_version": verified.protocol_version,
            "raw_manifest_sha256": verified.raw_manifest_sha256,
            "graded_manifest_sha256": verified.graded_manifest_sha256,
            "gold_sha256": verified.gold_sha256,
        },
        "semantic_calls": semantic_calls,
        "three_call_trajectory_count": three_call,
        "stable_semantic_failures": stable_failures,
        "deduplicated_calls_only_upper_bound": calls_upper,
        "calls_only_upper_bound_ratio": call_ratio,
        "duplicate_successful_observation_count": duplicate_total,
        "by_stratum_calls_tokens": by_stratum,
        "counterfactual_decision_invariance": invariance,
        "within_policy_adaptation_accuracy": (
            round(sum(adaptation_values) / len(adaptation_values), 6)
            if adaptation_values
            else None
        ),
        "cross_policy_semantic_sensitivity": None,
        "fixed_table_solvability": fixed_table_solvability,
        "post_observation_terminal_rate": terminal_rates,
    }
    if require_batch5d_signature:
        _assert_batch5d_signature(report)

    target.mkdir(parents=True, exist_ok=True)
    trajectory_path = target / "trajectories.jsonl"
    trajectory_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in trajectories),
        encoding="utf-8",
    )
    report_path = target / "replay_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    hashes_path = target / "hashes.json"
    hashes_path.write_text(
        json.dumps(
            {
                "schema_version": "q5-replay-hashes-v1",
                "artifacts": {
                    trajectory_path.name: q5_sha256_file(trajectory_path),
                    report_path.name: q5_sha256_file(report_path),
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if _directory_hashes(root) != source_hashes_before:
        raise RuntimeError("Q5 replay mutated the verified source run")
    return report


def _counterfactual_invariance(
    rows: list[dict[str, Any]],
    gold: dict[str, Any],
) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for case_id, case_gold in gold.items():
        for tag in case_gold.gold_reason_tags:
            if tag.startswith("counterfactual_group_"):
                groups[tag].append(case_id)
    output: list[dict[str, Any]] = []
    for group, case_ids in sorted(groups.items()):
        if len(case_ids) < 2:
            continue
        expected = {
            tuple(gold[case_id].allowed_terminal_actions) for case_id in case_ids
        }
        if len(expected) < 2:
            continue
        for system in _SEMANTIC_SYSTEMS:
            for run_index in sorted(
                {row["run_index"] for row in rows if row["system"] == system}
            ):
                selected = [
                    row
                    for row in rows
                    if row["system"] == system
                    and row["run_index"] == run_index
                    and row["case_id"] in case_ids
                ]
                if len(selected) != len(case_ids):
                    raise ValueError("incomplete Q5 counterfactual replay group")
                actions = sorted({row["terminal_action"] for row in selected})
                output.append(
                    {
                        "group": group,
                        "system": system,
                        "run_index": run_index,
                        "case_ids": sorted(case_ids),
                        "terminal_actions": actions,
                        "decision_invariant": len(actions) == 1,
                    }
                )
    return output


def _stratum_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for system in sorted({row["system"] for row in rows}):
        output[system] = {}
        for stratum in sorted({row["stratum"] for row in rows}):
            selected = [
                row
                for row in rows
                if row["system"] == system and row["stratum"] == stratum
            ]
            output[system][stratum] = {
                "calls": sum(row["llm_calls"] for row in selected),
                "tokens": sum(row["total_tokens"] for row in selected),
            }
    return output


def _assert_batch5d_signature(report: dict[str, Any]) -> None:
    expected = {
        "semantic_calls": {_LLM: 82, _HYBRID: 82},
        "three_call_trajectory_count": {_LLM: 13, _HYBRID: 13},
        "stable_semantic_failures": [
            "q5-dev-s01",
            "q5-dev-s04",
            "q5-dev-s06",
            "q5-dev-s10",
            "q5-dev-s12",
        ],
        "deduplicated_calls_only_upper_bound": {_LLM: 132, _HYBRID: 78},
        "calls_only_upper_bound_ratio": 0.590909,
    }
    for field, value in expected.items():
        if report.get(field) != value:
            raise ValueError(f"Batch 5-D replay signature mismatch: {field}")


def _trial_tuple(row: dict[str, Any]) -> tuple[str, str, int]:
    return str(row["case_id"]), str(row["system"]), int(row["run_index"])


def _optional_boolean_rate(values: Any) -> float | None:
    present = [value for value in values if isinstance(value, bool)]
    return round(sum(present) / len(present), 6) if present else None


def _directory_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }
