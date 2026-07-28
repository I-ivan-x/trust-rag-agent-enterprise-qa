from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval.q5_provenance import verify_q5_graded_run
from app.eval.q5_replay import replay_q5_graded_run

V3 = Path("data/q5/archive/dev-v3")
V4 = Path("data/q5/dev")
V3_REAL = Path(
    "data/eval_runs/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3"
)


def test_q5_dev_v4_diff_is_limited_to_frozen_clarity_and_provenance() -> None:
    assert (V3 / "environment.jsonl").read_bytes() == (
        V4 / "environment.jsonl"
    ).read_bytes()
    assert (V3 / "gold.jsonl").read_bytes() == (V4 / "gold.jsonl").read_bytes()

    v3_tasks = _jsonl(V3 / "tasks.jsonl")
    v4_tasks = _jsonl(V4 / "tasks.jsonl")
    assert len(v3_tasks) == len(v4_tasks) == 36
    for old, new in zip(v3_tasks, v4_tasks, strict=True):
        assert old["case_id"] == new["case_id"]
        changed = dict(new)
        changed["corpus_namespace"] = old["corpus_namespace"]
        assert changed == old
        assert new["corpus_namespace"] == old["corpus_namespace"].replace(
            "_v3", "_v4"
        )

    v3_runtime = _jsonl(V3 / "runtime_cases.jsonl")
    v4_runtime = _jsonl(V4 / "runtime_cases.jsonl")
    changed_text: dict[str, set[tuple[str, str]]] = {}
    for old, new in zip(v3_runtime, v4_runtime, strict=True):
        assert old["case_id"] == new["case_id"]
        pairs = _normalize_runtime_versions_and_collect_text(old, new)
        if pairs:
            changed_text[old["case_id"]] = pairs
    assert set(changed_text) == {"q5-dev-s02", "q5-dev-s11"}
    assert changed_text["q5-dev-s02"] == {
        (
            "resource:settlement-worker violates policy:change-control. The current "
            "exception state must be observed. A matching active waiver pauses "
            "remediation for human review; a waiver for another deployment scope leaves "
            "the violation actionable.",
            "resource:settlement-worker violates policy:change-control. The current "
            "exception state must be observed. A matching active waiver pauses "
            "remediation for human review; a waiver for another deployment scope requires "
            "a remediation ticket because the violation remains actionable.",
        )
    }
    assert all(
        "routes outage ownership to human review" in new
        for _, new in changed_text["q5-dev-s11"]
    )

    provenance = json.loads((V4 / "corpus/provenance.json").read_text("utf-8"))
    assert provenance["dataset_version"] == "v4"
    assert provenance["revision_reason"] == "post_v3_real_dev_clarity_revision"


def test_q5_v3_real_replay_identifies_exact_f18_cases_without_mutation(
    tmp_path: Path,
) -> None:
    if not V3_REAL.exists():
        pytest.skip("local sealed Q5 v3 real run is absent from the public checkout")
    before = {
        path.name: path.read_bytes()
        for path in V3_REAL.iterdir()
        if path.is_file()
    }
    verified = verify_q5_graded_run(V3_REAL, V3 / "gold.jsonl")
    assert verified.protocol_version == "v3"
    report = replay_q5_graded_run(
        V3_REAL,
        V3 / "gold.jsonl",
        tmp_path / "v3-f18-replay",
    )
    expected = [
        "q5-dev-s02",
        "q5-dev-s04",
        "q5-dev-s06",
        "q5-dev-s07",
        "q5-dev-s11",
    ]
    assert report["F18_policy_binding_failure_case_ids"] == {
        "q5_llm_agent": expected,
        "q5_hybrid_agent": expected,
    }
    assert before == {
        path.name: path.read_bytes()
        for path in V3_REAL.iterdir()
        if path.is_file()
    }


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def _normalize_runtime_versions_and_collect_text(
    old: object,
    new: object,
) -> set[tuple[str, str]]:
    changed: set[tuple[str, str]] = set()

    def visit(left: object, right: object) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            assert set(left) == set(right)
            text_changed = left.get("text") != right.get("text")
            for key in left:
                if key == "version":
                    assert left[key] == "q5-dev-v1"
                    assert right[key] == "q5-dev-v4"
                elif key == "text" and left[key] != right[key]:
                    changed.add((str(left[key]), str(right[key])))
                elif text_changed and key in {"char_count", "token_count"}:
                    assert right["char_count"] == len(str(right["text"]))
                    assert right["token_count"] == len(str(right["text"]).split())
                else:
                    visit(left[key], right[key])
            return
        if isinstance(left, list) and isinstance(right, list):
            assert len(left) == len(right)
            for left_item, right_item in zip(left, right, strict=True):
                visit(left_item, right_item)
            return
        assert left == right

    visit(old, new)
    return changed
