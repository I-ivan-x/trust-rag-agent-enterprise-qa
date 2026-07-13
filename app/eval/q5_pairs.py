"""Strict crossed-counterfactual contracts and protocol-v3 pair metrics."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.schemas.q5_task import Q5Gold

WITHIN_PREFIX = "within_policy_group_"
CROSS_PREFIX = "cross_policy_group_"
VARIANT_PREFIX = "policy_variant_"
FAMILY_PREFIX = "semantic_family_"


@dataclass(frozen=True)
class Q5PairAssignment:
    case_id: str
    family: str
    variant: str
    within_group: str
    cross_group: str
    required_tool: str
    observation_signature: str


def validate_q5_crossed_pair_design(
    gold: Mapping[str, Q5Gold],
    *,
    observation_signatures: Mapping[str, str],
) -> dict[str, Q5PairAssignment]:
    """Validate the sealed 2x2 design and return one assignment per semantic case."""

    assignments: dict[str, Q5PairAssignment] = {}
    for case_id, row in gold.items():
        pair_tags = [
            tag
            for tag in row.gold_reason_tags
            if tag.startswith((WITHIN_PREFIX, CROSS_PREFIX, VARIANT_PREFIX))
        ]
        if row.stratum.value != "semantic":
            if pair_tags:
                raise ValueError(f"non-semantic Q5 case carries pair tags: {case_id}")
            continue
        within = _one_tag(row.gold_reason_tags, WITHIN_PREFIX, case_id)
        cross = _one_tag(row.gold_reason_tags, CROSS_PREFIX, case_id)
        variant = _one_tag(row.gold_reason_tags, VARIANT_PREFIX, case_id)
        family = _one_tag(row.gold_reason_tags, FAMILY_PREFIX, case_id)
        if len(row.required_observations) != 1:
            raise ValueError(f"semantic Q5 case must require exactly one tool: {case_id}")
        signature = observation_signatures.get(case_id)
        if not signature:
            raise ValueError(f"semantic Q5 observation signature is missing: {case_id}")
        assignments[case_id] = Q5PairAssignment(
            case_id=case_id,
            family=family,
            variant=variant,
            within_group=within,
            cross_group=cross,
            required_tool=str(row.required_observations[0]),
            observation_signature=signature,
        )

    if len(assignments) != 12:
        raise ValueError(
            "Q5 v3 crossed design requires exactly 12 semantic cases, "
            f"got {len(assignments)}"
        )
    _validate_axis(assignments, gold, axis="within")
    _validate_axis(assignments, gold, axis="cross")
    return assignments


def q5_environment_observation_signature(
    environment: Mapping[str, Any],
    required_tool: str,
) -> str:
    """Derive the expected typed state without using task prose or label tags."""

    field = {
        "lookup_policy_exception": "policy_exceptions",
        "inspect_change_state": "change_states",
        "inspect_incident_impact": "incident_impacts",
    }.get(required_tool)
    if field is None:
        raise ValueError(f"unsupported Q5 observation tool in pair design: {required_tool}")
    values = environment.get(field)
    if not isinstance(values, Mapping) or len(values) != 1:
        raise ValueError(
            f"Q5 pair environment must expose exactly one {field} entry"
        )
    payload = next(iter(values.values()))
    if not isinstance(payload, Mapping):
        raise ValueError("Q5 pair environment state must be an object")
    state = {key: payload[key] for key in ("status", "scope") if key in payload}
    if "status" not in state:
        raise ValueError("Q5 pair observation signature requires status")
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def q5_tool_observation_signature(event: Mapping[str, Any]) -> str | None:
    if event.get("status") not in {"ok", "not_found"}:
        return None
    payload = event.get("observation")
    if not isinstance(payload, Mapping):
        return None
    state = {key: payload[key] for key in ("status", "scope") if key in payload}
    if "status" not in state:
        return None
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_q5_crossed_pair_metrics(
    rows: Sequence[dict[str, Any]],
    *,
    k: int,
) -> dict[str, Any]:
    """Compute strict per-index pair success; incomplete pairing is an error."""

    semantic = [row for row in rows if row.get("stratum") == "semantic"]
    assigned = [row for row in semantic if row.get("within_policy_group")]
    if not assigned:
        return {
            "within_policy_pair_success": None,
            "within_policy_adaptation_accuracy": None,
            "within_policy_paired_count": 0,
            "within_policy_pair_successes": 0,
            "within_policy_failure_case_ids": [],
            "within_policy_pair_groups": [],
            "cross_policy_pair_success": None,
            "cross_policy_semantic_sensitivity": None,
            "cross_policy_paired_count": 0,
            "cross_policy_pair_successes": 0,
            "cross_policy_failure_case_ids": [],
            "cross_policy_pair_groups": [],
        }
    if len(assigned) != len(semantic):
        raise ValueError("Q5 semantic rows have incomplete crossed-pair assignments")
    within = _axis_metrics(assigned, k=k, field="within_policy_group")
    cross = _axis_metrics(assigned, k=k, field="cross_policy_group")
    return {
        "within_policy_pair_success": within["rate"],
        "within_policy_adaptation_accuracy": within["rate"],
        "within_policy_paired_count": within["paired_count"],
        "within_policy_pair_successes": within["successes"],
        "within_policy_failure_case_ids": within["failure_case_ids"],
        "within_policy_pair_groups": within["groups"],
        "cross_policy_pair_success": cross["rate"],
        "cross_policy_semantic_sensitivity": cross["rate"],
        "cross_policy_paired_count": cross["paired_count"],
        "cross_policy_pair_successes": cross["successes"],
        "cross_policy_failure_case_ids": cross["failure_case_ids"],
        "cross_policy_pair_groups": cross["groups"],
    }


def _one_tag(tags: Sequence[str], prefix: str, case_id: str) -> str:
    matches = [tag for tag in tags if tag.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(
            f"Q5 semantic case must declare exactly one {prefix} tag: {case_id}"
        )
    suffix = matches[0].removeprefix(prefix)
    if not suffix:
        raise ValueError(f"Q5 semantic case has empty {prefix} tag: {case_id}")
    return matches[0]


def _validate_axis(
    assignments: Mapping[str, Q5PairAssignment],
    gold: Mapping[str, Q5Gold],
    *,
    axis: str,
) -> None:
    groups: dict[str, list[Q5PairAssignment]] = defaultdict(list)
    field = "within_group" if axis == "within" else "cross_group"
    for assignment in assignments.values():
        groups[getattr(assignment, field)].append(assignment)
    if len(groups) != 6:
        raise ValueError(f"Q5 {axis} axis requires exactly six pair groups")
    for group, members in sorted(groups.items()):
        if len(members) != 2:
            raise ValueError(f"Q5 {axis} group must contain exactly two cases: {group}")
        families = {item.family for item in members}
        tools = {item.required_tool for item in members}
        variants = {item.variant for item in members}
        signatures = {item.observation_signature for item in members}
        actions = {
            tuple(sorted(gold[item.case_id].allowed_terminal_actions))
            for item in members
        }
        valid = bool(
            len(families) == 1
            and len(tools) == 1
            and len(actions) == 2
            and (
                (len(variants) == 1 and len(signatures) == 2)
                if axis == "within"
                else (len(variants) == 2 and len(signatures) == 1)
            )
        )
        if not valid:
            raise ValueError(f"Q5 {axis} pair contract mismatch: {group}")


def _axis_metrics(
    rows: Sequence[dict[str, Any]],
    *,
    k: int,
    field: str,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()
    for row in rows:
        case_id = str(row.get("case_id") or "")
        run_index = row.get("run_index")
        group = row.get(field)
        if not case_id or type(run_index) is not int or not isinstance(group, str):
            raise ValueError("Q5 pair metric row has invalid identity")
        key = (case_id, run_index)
        if key in seen:
            raise ValueError(f"duplicate Q5 pair metric trial: {key}")
        seen.add(key)
        groups[group].append(row)
    if len(groups) != 6:
        raise ValueError(f"Q5 pair metrics require six groups for {field}")

    paired_count = 0
    successes = 0
    failure_ids: set[str] = set()
    details: list[dict[str, Any]] = []
    expected_indexes = set(range(1, k + 1))
    for group, members in sorted(groups.items()):
        case_ids = sorted({str(row["case_id"]) for row in members})
        if len(case_ids) != 2:
            raise ValueError(f"Q5 pair metric group is not binary: {group}")
        by_index: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in members:
            by_index[int(row["run_index"])].append(row)
        if set(by_index) != expected_indexes:
            raise ValueError(f"Q5 pair metric run-index matrix is incomplete: {group}")
        group_successes = 0
        group_failure_ids: set[str] = set()
        for run_index in sorted(by_index):
            pair = by_index[run_index]
            if len(pair) != 2 or {str(row["case_id"]) for row in pair} != set(case_ids):
                raise ValueError(f"Q5 pair metric trial is incomplete: {group}|{run_index}")
            paired_count += 1
            success = all(
                row.get("trajectory_qualified_success") is True for row in pair
            )
            successes += int(success)
            group_successes += int(success)
            if not success:
                failed = {
                    str(row["case_id"])
                    for row in pair
                    if row.get("trajectory_qualified_success") is not True
                }
                failure_ids.update(failed)
                group_failure_ids.update(failed)
        details.append(
            {
                "group": group,
                "case_ids": case_ids,
                "paired_count": k,
                "successes": group_successes,
                "failure_case_ids": sorted(group_failure_ids),
            }
        )
    return {
        "rate": round(successes / paired_count, 6),
        "paired_count": paired_count,
        "successes": successes,
        "failure_case_ids": sorted(failure_ids),
        "groups": details,
    }
