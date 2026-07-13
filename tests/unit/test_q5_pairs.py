from __future__ import annotations

import inspect
from copy import deepcopy

import pytest

from app.eval.q5_dataset import load_q5_environment, load_q5_gold, load_q5_tasks
from app.eval.q5_pairs import (
    compute_q5_crossed_pair_metrics,
    q5_environment_observation_signature,
    validate_q5_crossed_pair_design,
)
from app.govern.q5_rule_policy import (
    Q5RuleAgentPolicy,
    q5_fixed_table_runtime_proposal,
)


def _design():
    tasks = {task.case_id: task for task in load_q5_tasks("data/q5/dev/tasks.jsonl")}
    environment = load_q5_environment("data/q5/dev/environment.jsonl")
    gold = load_q5_gold("data/q5/dev/gold.jsonl")
    signatures = {
        case_id: q5_environment_observation_signature(
            environment[tasks[case_id].environment_ref].model_dump(mode="json"),
            row.required_observations[0],
        )
        for case_id, row in gold.items()
        if row.stratum.value == "semantic"
    }
    return gold, signatures


def test_q5_headline_rule_baseline_has_no_label_or_pair_tag_access() -> None:
    signature = inspect.signature(q5_fixed_table_runtime_proposal)
    source = inspect.getsource(q5_fixed_table_runtime_proposal).lower()

    assert list(signature.parameters) == ["context"]
    assert Q5RuleAgentPolicy.policy_source == "rule"
    for forbidden in ("gold", "stratum", "within_policy", "cross_policy", "group_"):
        assert forbidden not in source


def test_q5_crossed_design_has_six_closed_pairs_per_axis() -> None:
    gold, signatures = _design()

    assignments = validate_q5_crossed_pair_design(
        gold,
        observation_signatures=signatures,
    )

    assert len(assignments) == 12
    assert len({item.within_group for item in assignments.values()}) == 6
    assert len({item.cross_group for item in assignments.values()}) == 6


@pytest.mark.parametrize("mutation", ["missing_tag", "duplicate_group", "state"])
def test_q5_crossed_design_tamper_fails_closed(mutation: str) -> None:
    gold, signatures = _design()
    gold = dict(gold)
    if mutation == "missing_tag":
        row = gold["q5-dev-s01"]
        gold[row.case_id] = row.model_copy(
            update={
                "gold_reason_tags": [
                    tag
                    for tag in row.gold_reason_tags
                    if not tag.startswith("within_policy_group_")
                ]
            }
        )
    elif mutation == "duplicate_group":
        row = gold["q5-dev-s03"]
        gold[row.case_id] = row.model_copy(
            update={
                "gold_reason_tags": [
                    "within_policy_group_policy_waiver"
                    if tag.startswith("within_policy_group_")
                    else tag
                    for tag in row.gold_reason_tags
                ]
            }
        )
    else:
        signatures = dict(signatures)
        signatures["q5-dev-s03"] = '{"scope":"tampered","status":"active"}'

    with pytest.raises(ValueError, match="Q5"):
        validate_q5_crossed_pair_design(
            gold,
            observation_signatures=signatures,
        )


def test_q5_pair_metrics_report_counts_successes_and_failure_ids() -> None:
    gold, signatures = _design()
    assignments = validate_q5_crossed_pair_design(
        gold,
        observation_signatures=signatures,
    )
    rows = []
    for assignment in assignments.values():
        for run_index in range(1, 4):
            rows.append(
                {
                    "case_id": assignment.case_id,
                    "run_index": run_index,
                    "stratum": "semantic",
                    "within_policy_group": assignment.within_group,
                    "cross_policy_group": assignment.cross_group,
                    "trajectory_qualified_success": assignment.case_id
                    != "q5-dev-s03",
                }
            )

    metrics = compute_q5_crossed_pair_metrics(rows, k=3)

    assert metrics["within_policy_paired_count"] == 18
    assert metrics["within_policy_pair_successes"] == 15
    assert metrics["within_policy_failure_case_ids"] == ["q5-dev-s03"]
    assert metrics["cross_policy_paired_count"] == 18
    assert metrics["cross_policy_pair_successes"] == 15
    assert metrics["cross_policy_failure_case_ids"] == ["q5-dev-s03"]

    incomplete = deepcopy(rows[:-1])
    with pytest.raises(ValueError, match="incomplete"):
        compute_q5_crossed_pair_metrics(incomplete, k=3)
