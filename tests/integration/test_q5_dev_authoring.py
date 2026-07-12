from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_dataset import load_q5_gold, load_q5_tasks
from app.eval.q5_pre_run import (
    check_q5_pre_run,
    q5_semantic_query_state_disclosures,
)
from scripts.author_q5_dev import main as author_q5_dev

Q5_DEV_ROOT = Path("data/q5/dev")
Q5_DEV_V1_ARCHIVE = Path("data/q5/archive/dev-v1")


def test_formal_q5_dev_authoring_passes_static_pre_run() -> None:
    report = check_q5_pre_run(Q5_DEV_ROOT)

    assert report.valid is True
    assert report.task_count == report.environment_count == 36
    assert report.runtime_case_count == report.gold_count == 36
    assert report.stratum_counts == {
        "adversarial": 12,
        "deterministic": 12,
        "semantic": 12,
    }
    assert report.semantic_family_counts == {
        "semantic_family_change_state": 4,
        "semantic_family_incident_impact": 4,
        "semantic_family_policy_exception": 4,
    }
    assert report.checked_prompt_count == 36
    assert report.blocked_chunk_count == 3
    assert all(report.checks.values())

    persisted = json.loads((Q5_DEV_ROOT / "pre_run.json").read_text(encoding="utf-8"))
    assert persisted == report.model_dump(mode="json")


def test_q5_dev_authoring_is_reproducible_in_an_isolated_root(tmp_path: Path) -> None:
    output = tmp_path / "q5-dev"

    payload = author_q5_dev(["--output-root", str(output)])

    assert payload["task_count"] == 36
    assert payload["pre_run_valid"] is True
    assert check_q5_pre_run(output).valid is True


def test_q5_dev_semantic_queries_form_six_action_divergent_pairs() -> None:
    tasks = {task.case_id: task for task in load_q5_tasks(Q5_DEV_ROOT / "tasks.jsonl")}
    gold = load_q5_gold(Q5_DEV_ROOT / "gold.jsonl")
    groups: dict[str, list[tuple[tuple[str, ...], tuple[str, ...]]]] = {}

    for case_id, row in gold.items():
        if row.stratum.value != "semantic":
            continue
        task = tasks[case_id]
        assert q5_semantic_query_state_disclosures(
            task,
            required_tools=row.required_observations,
        ) == []
        group = next(
            tag.removeprefix("counterfactual_group_")
            for tag in row.gold_reason_tags
            if tag.startswith("counterfactual_group_")
        )
        groups.setdefault(group, []).append(
            (
                tuple(
                    sorted(
                        str(getattr(action, "value", action))
                        for action in row.allowed_terminal_actions
                    )
                ),
                tuple(
                    sorted(
                        str(getattr(tool, "value", tool))
                        for tool in row.required_observations
                    )
                ),
            )
        )

    assert len(groups) == 6
    for members in groups.values():
        assert len(members) == 2
        assert len({member[0] for member in members}) == 2
        assert len({member[1] for member in members}) == 1


@pytest.mark.parametrize(
    ("case_id", "leaking_suffix"),
    [
        ("q5-dev-s01", " The exception is active."),
        ("q5-dev-s05", " The change is completed."),
        ("q5-dev-s09", " The current impact is an outage."),
    ],
)
def test_q5_semantic_state_disclosure_detector_fails_closed(
    case_id: str,
    leaking_suffix: str,
) -> None:
    tasks = {task.case_id: task for task in load_q5_tasks(Q5_DEV_ROOT / "tasks.jsonl")}
    gold = load_q5_gold(Q5_DEV_ROOT / "gold.jsonl")
    task = tasks[case_id].model_copy(update={"query": tasks[case_id].query + leaking_suffix})

    assert q5_semantic_query_state_disclosures(
        task,
        required_tools=gold[case_id].required_observations,
    )


def test_q5_dev_v1_archive_preserves_real_run_dataset_hashes() -> None:
    expected = {
        "tasks.jsonl": "dabe8840c9a4ab63cc219bb574f312f25f8b674964e4717b2f57ffc14ad32047",
        "runtime_cases.jsonl": "4f6614bb43492d34a4a6b4cf4deebc28775a08e9527d45b520e700669c105a9f",
        "environment.jsonl": "6a91c1919df06106ff50af6f7a0a2eeccc7011b678bbf5f7a74d8310d52ecd5e",
        "gold.jsonl": "b8cb9a9a624aaabb72cf1ca4c5a6de9c0d7a4570053d5989acb3c9ecf1f5e839",
    }

    assert {
        name: hashlib.sha256((Q5_DEV_V1_ARCHIVE / name).read_bytes()).hexdigest()
        for name in expected
    } == expected


def test_q5_test_does_not_inherit_dev_counterfactual_group_contract(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "q5-test"
    shutil.copytree(Q5_DEV_ROOT, copied)
    gold_path = copied / "gold.jsonl"
    rows = [
        json.loads(line)
        for line in gold_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        row["gold_reason_tags"] = [
            tag
            for tag in row["gold_reason_tags"]
            if not tag.startswith("counterfactual_group_")
        ]
    gold_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    report = check_q5_pre_run(
        copied,
        dataset_partition="test",
        verify_receipt=False,
    )

    assert report.checks["semantic_counterfactual_pairs"] is True


def test_q5_pre_run_rejects_acl_overlap_tamper(tmp_path: Path) -> None:
    copied = tmp_path / "q5-dev"
    shutil.copytree(Q5_DEV_ROOT, copied)
    runtime_path = copied / "runtime_cases.jsonl"
    rows = [
        json.loads(line)
        for line in runtime_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    row = next(item for item in rows if item["case_id"] == "q5-dev-a04")
    blocked = row["pass_result"]["acl_decision"]["blocked_chunks"][0]
    row["pass_result"]["acl_decision"]["surviving_chunks"].append(blocked)
    runtime_path.write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in rows) + "\n",
        encoding="utf-8",
    )

    report = check_q5_pre_run(copied)

    assert report.valid is False
    assert report.checks["runtime_gate_replay"] is False
    assert report.checks["pre_run_receipt"] is False
