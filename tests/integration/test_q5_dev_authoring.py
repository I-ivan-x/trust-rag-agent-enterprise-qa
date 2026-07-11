from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.eval.q5_pre_run import check_q5_pre_run
from scripts.author_q5_dev import main as author_q5_dev

Q5_DEV_ROOT = Path("data/q5/dev")


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
