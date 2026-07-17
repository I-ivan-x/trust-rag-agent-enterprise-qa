"""Rebuild the frozen Q4 trajectory source used by the public control room.

This historical-source helper reads the ignored Q4 result/trace files and the
tracked Q4 action gold, then rewrites only ``frontend/src/data/trajectories.json``.
The public page never consumes this file directly: ``build_control_room_snapshot.py``
binds its committed blob and emits a runtime-only subset without gold fields.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Q4 = ROOT / "data" / "eval_runs" / "q4-p5-selection-calibrated"
TEST_GOLD = ROOT / "data" / "gold_eval" / "ops_runbook_action_v1_test.jsonl"
OUTPUT = ROOT / "frontend" / "src" / "data" / "trajectories.json"
RULE = "final_governed_rule"
PICKS = ("ora-t01", "ora-t05", "ora-t12", "ora-t15", "ora-t19")


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def build_trajectories() -> list[dict]:
    results = {
        row["case_id"]: row
        for row in _load_jsonl(Q4 / "results.jsonl")
        if row["system_name"] == RULE and row["run_index"] == 1
    }
    traces = {
        row["case_id"]: row
        for row in _load_jsonl(Q4 / "traces.jsonl")
        if row["system_name"] == RULE and row["run_index"] == 1
    }
    gold = {row["case_id"]: row for row in _load_jsonl(TEST_GOLD)}
    output = []
    for case_id in PICKS:
        result, trace, case_gold = results[case_id], traces[case_id], gold[case_id]
        output.append(
            {
                "case_id": case_id,
                "query": case_gold["query"],
                "user_role": case_gold["user_role"],
                "authorized": result["authorized"],
                "gold_action": result["gold_action"],
                "read": {
                    "retrieved": len(trace.get("retrieved_chunk_ids") or []),
                    "surviving": len(trace.get("surviving_chunk_ids") or []),
                    "blocked": len(trace.get("blocked_chunk_ids") or []),
                    "citations": (trace.get("sink_record") or {}).get(
                        "evidence_citations", []
                    )[:3],
                },
                "detect": {
                    "conditions": result.get("detected_conditions") or [],
                    "authorized_actor": result.get("authorized_actor"),
                    "evidence_decision": result.get("evidence_decision"),
                },
                "act": {
                    "proposed_action": result["proposed_action"],
                    "controller_source": result.get("controller_source"),
                    "risk_tier": result.get("risk_tier"),
                },
                "govern": {
                    "validator_ok": result.get("validator_ok"),
                    "forced_action": result.get("forced_action"),
                    "approval_state": result.get("approval_state"),
                    "executed_side_effect": result.get("executed_side_effect"),
                    "sink_record_id": result.get("sink_record_id"),
                },
                "correct": result["proposed_action"] == result["gold_action"],
            }
        )
    return output


def main() -> None:
    OUTPUT.write_text(
        json.dumps(build_trajectories(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
