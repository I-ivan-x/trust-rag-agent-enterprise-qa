from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_dataset import load_q5_gold, load_q5_runtime_dataset, load_q5_tasks
from app.eval.q5_pre_run import (
    check_q5_pre_run,
    q5_semantic_query_state_disclosures,
)
from app.eval.q5_runner import load_q5_runtime_cases
from app.eval.q5_semantic_control import (
    execute_q5_semantic_table_rule_control,
    grade_q5_semantic_table_rule_control,
)
from scripts.author_q5_dev import main as author_q5_dev

Q5_DEV_ROOT = Path("data/q5/dev")
Q5_DEV_V1_ARCHIVE = Path("data/q5/archive/dev-v1")
Q5_DEV_V2_ARCHIVE = Path("data/q5/archive/dev-v2")


def _frozen_text_sha256(path: Path) -> str:
    raw = path.read_bytes()
    canonical = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(canonical.replace(b"\n", b"\r\n")).hexdigest()


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


def test_formal_q5_pre_run_receipt_is_checkout_eol_independent(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "q5-dev-lf"
    shutil.copytree(Q5_DEV_ROOT, copied)
    for path in copied.rglob("*"):
        if path.is_file() and path.suffix.lower() in {
            ".json",
            ".jsonl",
            ".md",
            ".txt",
            ".yaml",
            ".yml",
        }:
            raw = path.read_bytes()
            path.write_bytes(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))

    assert check_q5_pre_run(copied).valid is True


def test_q5_dev_authoring_is_reproducible_in_an_isolated_root(tmp_path: Path) -> None:
    output = tmp_path / "q5-dev"

    payload = author_q5_dev(["--output-root", str(output)])

    assert payload["task_count"] == 36
    assert payload["pre_run_valid"] is True
    assert check_q5_pre_run(output).valid is True
    frozen_outputs = [
        output / "tasks.jsonl",
        output / "environment.jsonl",
        output / "runtime_cases.jsonl",
        output / "gold.jsonl",
        *sorted((output / "corpus").rglob("*.json")),
        *sorted((output / "corpus").rglob("*.md")),
    ]
    for path in frozen_outputs:
        raw = path.read_bytes()
        assert b"\r\n" in raw
        assert b"\n" not in raw.replace(b"\r\n", b"")


def test_q5_dev_semantic_queries_form_crossed_counterfactual_pairs() -> None:
    tasks = {task.case_id: task for task in load_q5_tasks(Q5_DEV_ROOT / "tasks.jsonl")}
    gold = load_q5_gold(Q5_DEV_ROOT / "gold.jsonl")
    within_groups: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    cross_groups: dict[str, list[tuple[tuple[str, ...], str]]] = {}

    for case_id, row in gold.items():
        if row.stratum.value != "semantic":
            continue
        task = tasks[case_id]
        assert q5_semantic_query_state_disclosures(
            task,
            required_tools=row.required_observations,
        ) == []
        within_group = next(
            tag.removeprefix("within_policy_group_")
            for tag in row.gold_reason_tags
            if tag.startswith("within_policy_group_")
        )
        cross_group = next(
            tag.removeprefix("cross_policy_group_")
            for tag in row.gold_reason_tags
            if tag.startswith("cross_policy_group_")
        )
        variant = next(
            tag.removeprefix("policy_variant_")
            for tag in row.gold_reason_tags
            if tag.startswith("policy_variant_")
        )
        actions = tuple(
            sorted(
                str(getattr(action, "value", action))
                for action in row.allowed_terminal_actions
            )
        )
        within_groups.setdefault(within_group, []).append((actions, variant))
        cross_groups.setdefault(cross_group, []).append((actions, variant))

    assert len(within_groups) == len(cross_groups) == 6
    for members in within_groups.values():
        assert len(members) == 2
        assert len({member[0] for member in members}) == 2
        assert len({member[1] for member in members}) == 1
    for members in cross_groups.values():
        assert len(members) == 2
        assert len({member[0] for member in members}) == 2
        assert len({member[1] for member in members}) == 2


def test_q5_dev_v3_fixed_table_solvability_is_capped_at_half() -> None:
    dataset = load_q5_runtime_dataset(
        Q5_DEV_ROOT / "tasks.jsonl",
        Q5_DEV_ROOT / "environment.jsonl",
    )
    execution = execute_q5_semantic_table_rule_control(
        dataset.tasks,
        dataset.environment,
        load_q5_runtime_cases(Q5_DEV_ROOT / "runtime_cases.jsonl"),
        k=1,
    )
    report = grade_q5_semantic_table_rule_control(
        execution,
        load_q5_gold(Q5_DEV_ROOT / "gold.jsonl"),
    )

    assert report.semantic_trial_count == 12
    assert report.fixed_table_solvability == 0.5


@pytest.mark.parametrize(
    ("tag_prefix", "check_name"),
    [
        ("within_policy_group_", "semantic_within_policy_pairs"),
        ("cross_policy_group_", "semantic_cross_policy_pairs"),
    ],
)
def test_q5_dev_v3_crossed_pair_tamper_fails_closed(
    tmp_path: Path,
    tag_prefix: str,
    check_name: str,
) -> None:
    copied = tmp_path / f"q5-dev-{check_name}"
    shutil.copytree(Q5_DEV_ROOT, copied)
    gold_path = copied / "gold.jsonl"
    rows = [
        json.loads(line)
        for line in gold_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    row = next(item for item in rows if item["case_id"] == "q5-dev-s01")
    row["gold_reason_tags"] = [
        "tampered_group" if tag.startswith(tag_prefix) else tag
        for tag in row["gold_reason_tags"]
    ]
    gold_path.write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in rows) + "\n",
        encoding="utf-8",
    )

    report = check_q5_pre_run(copied)

    assert report.valid is False
    assert report.checks[check_name] is False
    assert report.checks["pre_run_receipt"] is False


def test_q5_dev_v3_observation_axis_tamper_fails_closed(tmp_path: Path) -> None:
    copied = tmp_path / "q5-dev-state-tamper"
    shutil.copytree(Q5_DEV_ROOT, copied)
    environment_path = copied / "environment.jsonl"
    rows = [
        json.loads(line)
        for line in environment_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    row = next(item for item in rows if item["environment_ref"] == "q5-dev-env-s03")
    exception = row["policy_exceptions"][
        "resource:invoice-renderer|policy:deployment-window"
    ]
    exception["scope"] = "staging"
    environment_path.write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in rows) + "\n",
        encoding="utf-8",
    )

    report = check_q5_pre_run(copied)

    assert report.valid is False
    assert report.checks["semantic_within_policy_pairs"] is False
    assert report.checks["semantic_cross_policy_pairs"] is False


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
        name: _frozen_text_sha256(Q5_DEV_V1_ARCHIVE / name)
        for name in expected
    } == expected


def test_q5_dev_v2_archive_preserves_batch5d_dataset_hashes() -> None:
    expected = {
        "tasks.jsonl": "eecc6bd418051638c687b4b86413dca94c4339ad36421c7576e4a4ec75ddb68f",
        "runtime_cases.jsonl": "07bc4992b6e6ccd13d71d8d3a90de0d81b33a6028146e46f53288f1df437aaeb",
        "environment.jsonl": "22a2a356ce35466a0cc7a8ff7f19d47919194ca7c8a6470af3488f805d4fb06a",
        "gold.jsonl": "e7c0e96e0eb50f752c2132a4c7ece7577b605d3c585c721a1a255aaf70772a32",
    }

    assert {
        name: _frozen_text_sha256(Q5_DEV_V2_ARCHIVE / name)
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
            if not tag.startswith(
                ("within_policy_group_", "cross_policy_group_", "policy_variant_")
            )
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

    assert report.checks["semantic_within_policy_pairs"] is True
    assert report.checks["semantic_cross_policy_pairs"] is True


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
