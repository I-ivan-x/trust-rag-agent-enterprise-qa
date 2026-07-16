"""Hash-closed offline Q5 counterfactual value ledger."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.eval.q5_provenance import (
    q5_read_json,
    q5_read_jsonl,
    q5_sha256_file,
    verify_q5_graded_run,
)
from app.govern.q5_loop import Q5AgentSystem

Q5_VALUE_LEDGER_SCHEMA = "q5-value-ledger-v2"
Q5_VALUE_SUMMARY_SCHEMA = "q5-value-summary-v2"
Q5_VALUE_HASHES_SCHEMA = "q5-value-hashes-v2"
Q5_VALUE_V1_HASHES_SCHEMA = "q5-value-hashes-v1"
Q5_VALUE_FILES = frozenset(
    {"value_ledger.jsonl", "value_summary.json", "value_report.md", "value_hashes.json"}
)
_SYSTEMS = tuple(system.value for system in Q5AgentSystem)
_FROZEN_VALUE_V1_ARTIFACTS = {
    "value_ledger.jsonl": "883c156cb6636a59fd0e6f29600fb4f0206f338ad9323c34cf335dafd3c458d3",
    "value_report.md": "edfd8e05dd37a7640a61cca68a66e0da5e37cab6f1b1129bf234df2f5cbf6bbd",
    "value_summary.json": "dc55954f77a50d9ab1c8abe13032799586139595717f2dd77e3b7b7d01fa8d64",
}


def build_q5_value_ledger(
    run_dir: Path | str,
    gold_path: Path | str,
    output_dir: Path | str,
) -> dict[str, Any]:
    source = Path(run_dir)
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(f"Q5 value-ledger output already exists: {target}")
    verified = verify_q5_graded_run(source, gold_path)
    ledger, summary, report = _derive_value_artifacts(source, verified.model_dump(mode="json"))
    target.mkdir(parents=True)
    _write_jsonl(target / "value_ledger.jsonl", ledger)
    _write_json(target / "value_summary.json", summary)
    (target / "value_report.md").write_text(report, encoding="utf-8")
    _write_json(
        target / "value_hashes.json",
        {
            "schema_version": Q5_VALUE_HASHES_SCHEMA,
            "artifacts": {
                name: q5_sha256_file(target / name)
                for name in sorted(Q5_VALUE_FILES - {"value_hashes.json"})
            },
        },
    )
    return verify_q5_value_ledger(source, gold_path, target)


def verify_q5_value_ledger(
    run_dir: Path | str,
    gold_path: Path | str,
    value_dir: Path | str,
) -> dict[str, Any]:
    source = Path(run_dir)
    target = Path(value_dir)
    actual = {path.name for path in target.iterdir()}
    if actual != Q5_VALUE_FILES:
        raise ValueError(
            "Q5 value artifact closure mismatch: "
            f"missing={sorted(Q5_VALUE_FILES - actual)}, "
            f"extra={sorted(actual - Q5_VALUE_FILES)}"
        )
    hashes = q5_read_json(target / "value_hashes.json")
    if hashes.get("schema_version") == Q5_VALUE_V1_HASHES_SCHEMA:
        return _verify_frozen_value_v1(source, gold_path, target, hashes)
    if (
        not isinstance(hashes, dict)
        or hashes.get("schema_version") != Q5_VALUE_HASHES_SCHEMA
        or set(hashes.get("artifacts") or {})
        != Q5_VALUE_FILES - {"value_hashes.json"}
    ):
        raise ValueError("Q5 value hash inventory is invalid")
    for name, expected in hashes["artifacts"].items():
        if expected != q5_sha256_file(target / name):
            raise ValueError(f"Q5 value artifact hash mismatch: {name}")
    verified = verify_q5_graded_run(source, gold_path)
    expected_ledger, expected_summary, expected_report = _derive_value_artifacts(
        source,
        verified.model_dump(mode="json"),
    )
    if q5_read_jsonl(target / "value_ledger.jsonl") != expected_ledger:
        raise ValueError("Q5 value ledger does not match verified source artifacts")
    if q5_read_json(target / "value_summary.json") != expected_summary:
        raise ValueError("Q5 value summary does not match verified source artifacts")
    if (target / "value_report.md").read_text(encoding="utf-8") != expected_report:
        raise ValueError("Q5 value report does not match verified source artifacts")
    return expected_summary


def _verify_frozen_value_v1(
    source: Path,
    gold_path: Path | str,
    target: Path,
    hashes: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the one committed 5-I v1 sidecar by its frozen byte inventory."""

    if hashes.get("artifacts") != _FROZEN_VALUE_V1_ARTIFACTS:
        raise ValueError("Q5 value v1 sidecar is not a frozen artifact")
    for name, expected_hash in _FROZEN_VALUE_V1_ARTIFACTS.items():
        if q5_sha256_file(target / name) != expected_hash:
            raise ValueError(f"Q5 value v1 artifact hash mismatch: {name}")
    verified = verify_q5_graded_run(source, gold_path)
    summary = q5_read_json(target / "value_summary.json")
    expected_source_hashes = {
        name: q5_sha256_file(source / name)
        for name in (
            "manifest.json",
            "graded_manifest.json",
            "graded_rows.jsonl",
            "policy_events.jsonl",
            "trajectory.jsonl",
        )
    }
    if (
        summary.get("schema_version") != "q5-value-summary-v1"
        or summary.get("source_run_id") != verified.run_id
        or summary.get("source_git_commit_sha") != verified.git_commit_sha
        or summary.get("source_hashes") != expected_source_hashes
    ):
        raise ValueError("Q5 value v1 source provenance mismatch")
    return summary


def _derive_value_artifacts(
    source: Path,
    verified: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    manifest = q5_read_json(source / "manifest.json")
    graded = q5_read_jsonl(source / "graded_rows.jsonl")
    policy = q5_read_jsonl(source / "policy_events.jsonl")
    trajectory = q5_read_jsonl(source / "trajectory.jsonl")
    case_ids = list(manifest.get("case_ids") or [])
    k = int(manifest.get("k") or 0)
    expected = {
        (case_id, system, run_index)
        for case_id in case_ids
        for system in _SYSTEMS
        for run_index in range(1, k + 1)
    }
    graded_by_key = _index_exact(graded, expected, "graded rows")
    policy_by_key = _group_steps(policy, expected, "policy events")
    trajectory_by_key = _group_steps(trajectory, expected, "trajectory")
    if len(case_ids) != 36 or k != 3 or len(expected) != 324:
        raise ValueError("Q5 value ledger requires the complete 36x3x3 matrix")

    ledger: list[dict[str, Any]] = []
    for case_id in sorted(case_ids):
        for run_index in range(1, k + 1):
            system_rows = {
                system: graded_by_key[(case_id, system, run_index)] for system in _SYSTEMS
            }
            rule = bool(system_rows[Q5AgentSystem.rule.value]["trajectory_qualified_success"])
            llm = bool(system_rows[Q5AgentSystem.llm.value]["trajectory_qualified_success"])
            hybrid = bool(
                system_rows[Q5AgentSystem.hybrid.value]["trajectory_qualified_success"]
            )
            value_class = "beneficial" if llm > rule else "harmful" if llm < rule else "neutral"
            oracle = max(rule, llm)
            semantic_row = system_rows[Q5AgentSystem.rule.value]
            for system in _SYSTEMS:
                key = (case_id, system, run_index)
                phase = _phase_ledger(
                    system_rows[system],
                    policy_by_key[key],
                    trajectory_by_key[key],
                )
                ledger.append(
                    {
                        "schema_version": Q5_VALUE_LEDGER_SCHEMA,
                        "case_id": case_id,
                        "system": system,
                        "run_index": run_index,
                        "stratum": semantic_row["stratum"],
                        "within_policy_group": semantic_row.get("within_policy_group"),
                        "cross_policy_group": semantic_row.get("cross_policy_group"),
                        "system_tq_outcome": bool(
                            system_rows[system]["trajectory_qualified_success"]
                        ),
                        "rule_tq_outcome": rule,
                        "llm_tq_outcome": llm,
                        "hybrid_tq_outcome": hybrid,
                        "value_class": value_class,
                        "oracle_outcome": oracle,
                        "hybrid_oracle_regret": int(oracle) - int(hybrid),
                        **phase,
                    }
                )
    source_hashes = {
        name: q5_sha256_file(source / name)
        for name in (
            "manifest.json",
            "graded_manifest.json",
            "graded_rows.jsonl",
            "policy_events.jsonl",
            "trajectory.jsonl",
        )
    }
    summary = _summarize_value_ledger(ledger)
    summary.update(
        {
            "schema_version": Q5_VALUE_SUMMARY_SCHEMA,
            "source_run_id": manifest["run_id"],
            "source_git_commit_sha": verified["git_commit_sha"],
            "source_hashes": source_hashes,
            "ledger_row_count": len(ledger),
            "trial_group_count": len(ledger) // len(_SYSTEMS),
            "source_trial_count": len(expected),
        }
    )
    return ledger, summary, _render_value_report(summary)


def _phase_ledger(
    result: Mapping[str, Any],
    policy: Sequence[Mapping[str, Any]],
    trajectory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    observation_sources: list[str] = []
    calls = Counter({"observation_planning": 0, "terminal_binding": 0, "other": 0})
    for event in policy:
        source = str(event.get("policy_source") or "")
        called = event.get("llm_called")
        if called != (source == "llm"):
            raise ValueError("Q5 value phase source/call ledger does not close")
        proposal = event.get("accepted_proposal")
        kind = proposal.get("kind") if isinstance(proposal, Mapping) else None
        if kind == "observe":
            observation_sources.append(source)
            if called:
                calls["observation_planning"] += 1
        elif kind == "terminal":
            if called:
                calls["terminal_binding"] += 1
        elif called:
            calls["other"] += 1
    terminal_events = [event for event in trajectory if event.get("event_type") == "terminal"]
    if len(terminal_events) != 1:
        raise ValueError("Q5 value ledger requires one terminal trajectory event")
    terminal_source = terminal_events[0].get("policy_source")
    if terminal_source not in {"rule", "llm"}:
        raise ValueError("Q5 value terminal policy source is invalid")
    if sum(calls.values()) != int(result.get("llm_calls") or 0):
        raise ValueError("Q5 value cognitive-phase call ledger does not close")
    return {
        "observation_policy_sources": observation_sources,
        "terminal_policy_source": terminal_source,
        "observation_planning_llm_calls": calls["observation_planning"],
        "terminal_binding_llm_calls": calls["terminal_binding"],
        "other_llm_calls": calls["other"],
        "total_llm_calls": sum(calls.values()),
    }


def _summarize_value_ledger(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expected_systems = set(_SYSTEMS)
    groups: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["case_id"]), int(row["run_index"]))].append(row)
    if len(rows) != 324 or len(groups) != 108 or any(
        {str(row["system"]) for row in group} != expected_systems
        or len(group) != len(expected_systems)
        for group in groups.values()
    ):
        raise ValueError("Q5 value ledger case/system/run matrix is incomplete")
    hybrid_rows = [
        row for row in rows if row["system"] == Q5AgentSystem.hybrid.value
    ]
    classes = Counter(str(row["value_class"]) for row in hybrid_rows)
    beneficial = [row for row in hybrid_rows if row["value_class"] == "beneficial"]
    harmful = [row for row in hybrid_rows if row["value_class"] == "harmful"]
    neutral = [row for row in hybrid_rows if row["value_class"] == "neutral"]
    total_calls = sum(int(row["total_llm_calls"]) for row in hybrid_rows)
    beneficial_capture_numerator = sum(
        row["terminal_policy_source"] == "llm"
        and bool(row["hybrid_tq_outcome"])
        for row in beneficial
    )
    beneficial_capture_denominator = len(beneficial)
    beneficial_capture_vacuous = beneficial_capture_denominator == 0
    beneficial_capture = (
        round(beneficial_capture_numerator / beneficial_capture_denominator, 6)
        if beneficial_capture_denominator
        else None
    )
    observation_global = sum(
        int(row["observation_planning_llm_calls"]) for row in hybrid_rows
    )
    observation_semantic = sum(
        int(row["observation_planning_llm_calls"])
        for row in hybrid_rows
        if row["stratum"] == "semantic"
    )
    observation_adversarial = sum(
        int(row["observation_planning_llm_calls"])
        for row in hybrid_rows
        if row["stratum"] == "adversarial"
    )
    terminal_global = sum(
        int(row["terminal_binding_llm_calls"]) for row in hybrid_rows
    )
    terminal_semantic = sum(
        int(row["terminal_binding_llm_calls"])
        for row in hybrid_rows
        if row["stratum"] == "semantic"
    )
    terminal_adversarial = sum(
        int(row["terminal_binding_llm_calls"])
        for row in hybrid_rows
        if row["stratum"] == "adversarial"
    )
    return {
        "value_class_counts": dict(sorted(classes.items())),
        "beneficial_group_count": len(beneficial),
        "beneficial_capture_numerator": beneficial_capture_numerator,
        "beneficial_capture_denominator": beneficial_capture_denominator,
        "beneficial_capture_vacuous": beneficial_capture_vacuous,
        "beneficial_value_capture": beneficial_capture,
        "harmful_terminal_llm_exposure": sum(
            row["terminal_policy_source"] == "llm" for row in harmful
        ),
        "neutral_terminal_llm_exposure": sum(
            row["terminal_policy_source"] == "llm" for row in neutral
        ),
        "hybrid_oracle_regret": round(
            sum(int(row["hybrid_oracle_regret"]) for row in hybrid_rows)
            / len(hybrid_rows),
            6,
        ),
        "hybrid_observation_planning_llm_calls_global": observation_global,
        "hybrid_observation_planning_llm_calls_semantic": observation_semantic,
        "hybrid_observation_planning_llm_calls_adversarial": observation_adversarial,
        "hybrid_terminal_binding_llm_calls_global": terminal_global,
        "hybrid_terminal_binding_llm_calls_semantic": terminal_semantic,
        "hybrid_terminal_binding_llm_calls_adversarial": terminal_adversarial,
        "phase_call_metric_scopes": {
            "global": "all_strata",
            "semantic": "semantic_stratum_only",
            "adversarial": "adversarial_stratum_only",
        },
        "hybrid_adversarial_llm_calls": sum(
            int(row["total_llm_calls"])
            for row in hybrid_rows
            if row["stratum"] == "adversarial"
        ),
        "hybrid_total_llm_calls": total_calls,
        "incremental_successes_per_100_calls": round(
            100
            * sum(
                int(row["hybrid_tq_outcome"]) - int(row["rule_tq_outcome"])
                for row in hybrid_rows
            )
            / total_calls,
            6,
        )
        if total_calls
        else 0.0,
        "within_policy_groups": _group_value_rows(
            hybrid_rows, "within_policy_group"
        ),
        "cross_policy_groups": _group_value_rows(
            hybrid_rows, "cross_policy_group"
        ),
    }


def _group_value_rows(
    rows: Sequence[Mapping[str, Any]],
    field: str,
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get(field):
            grouped[str(row[field])].append(row)
    return {
        group: {
            "paired_rows": len(values),
            "rule_successes": sum(bool(row["rule_tq_outcome"]) for row in values),
            "llm_successes": sum(bool(row["llm_tq_outcome"]) for row in values),
            "hybrid_successes": sum(bool(row["hybrid_tq_outcome"]) for row in values),
            "value_class_counts": dict(
                sorted(Counter(str(row["value_class"]) for row in values).items())
            ),
        }
        for group, values in sorted(grouped.items())
    }


def _index_exact(
    rows: Sequence[Any],
    expected: set[tuple[str, str, int]],
    label: str,
) -> dict[tuple[str, str, int], Mapping[str, Any]]:
    indexed: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"Q5 value {label} row is invalid")
        key = (str(row.get("case_id")), str(row.get("system")), int(row.get("run_index", 0)))
        if key not in expected or key in indexed:
            raise ValueError(f"Q5 value {label} has an extra or duplicate trial: {key}")
        indexed[key] = row
    if set(indexed) != expected:
        raise ValueError(f"Q5 value {label} trial matrix is incomplete")
    return indexed


def _group_steps(
    rows: Sequence[Any],
    expected: set[tuple[str, str, int]],
    label: str,
) -> dict[tuple[str, str, int], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str, int], list[Mapping[str, Any]]] = defaultdict(list)
    seen: set[tuple[tuple[str, str, int], int]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"Q5 value {label} row is invalid")
        key = (str(row.get("case_id")), str(row.get("system")), int(row.get("run_index", 0)))
        step = int(row.get("step_index", 0))
        if key not in expected or step < 1 or (key, step) in seen:
            raise ValueError(f"Q5 value {label} has invalid step provenance")
        seen.add((key, step))
        grouped[key].append(row)
    if set(grouped) != expected:
        raise ValueError(f"Q5 value {label} trial matrix is incomplete")
    for values in grouped.values():
        values.sort(key=lambda row: int(row["step_index"]))
    return grouped


def _render_value_report(summary: Mapping[str, Any]) -> str:
    capture = summary["beneficial_value_capture"]
    capture_text = "null (empty/vacuous)" if capture is None else f"{capture:.6f}"
    evidence_state = (
        "empty/vacuous" if summary["beneficial_capture_vacuous"] else "present"
    )
    return (
        "# Q5 Counterfactual Value Ledger\n\n"
        f"- Source run: `{summary['source_run_id']}`\n"
        f"- Beneficial evidence: `{evidence_state}`\n"
        f"- Beneficial groups: `{summary['beneficial_group_count']}`\n"
        f"- Beneficial value capture: `{capture_text}`\n"
        f"- Beneficial capture numerator/denominator: "
        f"`{summary['beneficial_capture_numerator']}/"
        f"{summary['beneficial_capture_denominator']}`\n"
        f"- Harmful terminal LLM exposure: `{summary['harmful_terminal_llm_exposure']}`\n"
        f"- Neutral terminal LLM exposure: `{summary['neutral_terminal_llm_exposure']}`\n"
        f"- Hybrid oracle regret: `{summary['hybrid_oracle_regret']:.6f}`\n"
        f"- Observation-planning calls (global/semantic/adversarial): "
        f"`{summary['hybrid_observation_planning_llm_calls_global']}/"
        f"{summary['hybrid_observation_planning_llm_calls_semantic']}/"
        f"{summary['hybrid_observation_planning_llm_calls_adversarial']}`\n"
        f"- Terminal-binding calls (global/semantic/adversarial): "
        f"`{summary['hybrid_terminal_binding_llm_calls_global']}/"
        f"{summary['hybrid_terminal_binding_llm_calls_semantic']}/"
        f"{summary['hybrid_terminal_binding_llm_calls_adversarial']}`\n"
        "- Actual observation topology: `3/0/3` "
        "(global/semantic/adversarial).\n"
        f"- Adversarial LLM calls: `{summary['hybrid_adversarial_llm_calls']}`\n"
        f"- Total Hybrid LLM calls: `{summary['hybrid_total_llm_calls']}`\n"
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
