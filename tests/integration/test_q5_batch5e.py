from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

from app.eval.q5_dataset import load_q5_gold, load_q5_runtime_dataset
from app.eval.q5_replay import replay_q5_graded_run
from app.eval.q5_runner import load_q5_runtime_cases
from app.eval.q5_semantic_control import (
    Q5SemanticTableRuleModel,
    execute_q5_semantic_table_rule_control,
    grade_q5_semantic_table_rule_control,
)

DEV_ROOT = Path("data/q5/archive/dev-v2")
BATCH5D_RUN = Path(
    "data/eval_runs/q5-dev-v2-real-deepseek-v4-flash-2224fc4-primary-k3"
)


def test_q5_semantic_table_control_is_runtime_only_and_reports_solvability() -> None:
    signature = inspect.signature(execute_q5_semantic_table_rule_control)
    source = inspect.getsource(Q5SemanticTableRuleModel.generate)
    assert "gold" not in signature.parameters
    for forbidden in ("gold", "stratum", "family", "group"):
        assert forbidden not in source.lower()

    dataset = load_q5_runtime_dataset(
        DEV_ROOT / "tasks.jsonl",
        DEV_ROOT / "environment.jsonl",
    )
    execution = execute_q5_semantic_table_rule_control(
        dataset.tasks,
        dataset.environment,
        load_q5_runtime_cases(DEV_ROOT / "runtime_cases.jsonl"),
    )
    report = grade_q5_semantic_table_rule_control(
        execution,
        load_q5_gold(DEV_ROOT / "gold.jsonl"),
    )

    assert report.semantic_trial_count == 12
    assert report.fixed_table_solvability == 1.0
    assert all(row["llm_calls"] in {0, 1, 2} for row in report.rows)


def test_q5_batch5d_read_only_replay_reproduces_sealed_diagnostic(
    tmp_path: Path,
) -> None:
    before = _file_hashes(BATCH5D_RUN)
    report = replay_q5_graded_run(
        BATCH5D_RUN,
        DEV_ROOT / "gold.jsonl",
        tmp_path / "replay",
        fixed_table_solvability=1.0,
        require_batch5d_signature=True,
    )

    assert report["semantic_calls"] == {
        "q5_llm_agent": 82,
        "q5_hybrid_agent": 82,
    }
    assert report["three_call_trajectory_count"] == {
        "q5_llm_agent": 13,
        "q5_hybrid_agent": 13,
    }
    assert report["stable_semantic_failures"] == [
        "q5-dev-s01",
        "q5-dev-s04",
        "q5-dev-s06",
        "q5-dev-s10",
        "q5-dev-s12",
    ]
    assert report["deduplicated_calls_only_upper_bound"] == {
        "q5_llm_agent": 132,
        "q5_hybrid_agent": 78,
    }
    assert report["calls_only_upper_bound_ratio"] == 0.590909
    assert report["fixed_table_solvability"] == 1.0
    assert _file_hashes(BATCH5D_RUN) == before


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.iterdir()
        if path.is_file()
    }
