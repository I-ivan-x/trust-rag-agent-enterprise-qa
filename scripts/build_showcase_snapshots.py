"""Build static, real-run data snapshots for the TrustRAG showcase frontend.

Reads the frozen q3-p7 / q4-p5 governance runs and emits JSON to
frontend/src/data/. All numbers are real run output (run_id stamped); the only
derived value is the analytic "escalate-all cheater" triad, computed from the
held-out test gold and explicitly labelled mode="analytic". No fabrication.

Reproduce:  python scripts/build_showcase_snapshots.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data" / "eval_runs"
Q3 = RUNS / "q3-p7-governance-ablation"
Q4 = RUNS / "q4-p5-selection-calibrated"
TEST_GOLD = ROOT / "data" / "gold_eval" / "ops_runbook_action_v1_test.jsonl"
OUT = ROOT / "frontend" / "src" / "data"

RULE = "final_governed_rule"
LLM = "final_governed_llm"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _metrics(summary: dict, system: str) -> dict:
    by = summary["governance_metrics"]["by_system"][system]
    keys = [
        "action_precision@authorized",
        "over_escalation_rate",
        "escalation_when_insufficient",
        "unauthorized_action_blocked",
        "anti_gaming_triad_ok",
    ]
    out = {k: by.get(k) for k in keys}
    pk = summary.get("governance_passk", {}).get("by_system", {}).get(system, {})
    out["pass_1"] = pk.get("pass_1_attempt_mean")
    out["pass_k"] = pk.get("pass_3")
    fa = summary["governance_attribution"]["failure_taxonomy"]
    out["F11"] = fa["F11_action_without_evidence"]
    out["F13"] = fa["F13_missed_escalation_unauth"]
    return out


def build_triad() -> dict:
    q3, q4 = _load_json(Q3 / "summary.json"), _load_json(Q4 / "summary.json")
    gold = _load_jsonl(TEST_GOLD)
    authorized = [c for c in gold if c.get("authorized") is True]
    auth_escalate = [c for c in authorized if c["gold_action"] == "escalate_to_human"]
    non_escalate = [c for c in gold if c["gold_action"] != "escalate_to_human"]
    cheater = {
        "label": "escalate-everything controller",
        "mode": "analytic",
        "note": "Computed from the held-out test gold: an all-escalate controller blocks every "
        "unauthorized action (1.0) but is useless. Shown to prove the triad catches gaming.",
        "action_precision@authorized": round(len(auth_escalate) / len(authorized), 4),
        "over_escalation_rate": round(len(non_escalate) / len(gold), 4),
        "unauthorized_action_blocked": 1.0,
        "anti_gaming_triad_ok": False,
    }
    return {
        "thresholds": {"AUTH_PRECISION_FLOOR": 0.60, "OVER_ESCALATION_CEIL": 0.30},
        "note": "Before = Q3 state on its 14-case ops set; After = Q4 state on the "
        "20-case held-out ops_test the calibration never tuned on. The eval set was expanded in "
        "Q4, so this is a Q3→Q4 state comparison, not a controlled same-set A/B. The load-bearing "
        "claim is the After "
        "itself: triad True on a held-out set, thresholds frozen.",
        "before": {
            "run_id": q3["run_id"],
            "split": "Q3 baseline · 14-case ops set",
            "rule": _metrics(q3, RULE),
        },
        "after": {
            "run_id": q4["run_id"],
            "split": "Q4 held-out · 20-case ops_test (never tuned on)",
            "rule": _metrics(q4, RULE),
            "llm_ablation": _metrics(q4, LLM),
        },
        "cheater": cheater,
        "headline_eligible": q4.get("governance_headline_eligible_by_system"),
    }


_PICKS = ["ora-t01", "ora-t05", "ora-t12", "ora-t15", "ora-t19"]


def build_trajectories() -> list[dict]:
    results = {
        (r["case_id"]): r
        for r in _load_jsonl(Q4 / "results.jsonl")
        if r["system_name"] == RULE and r["run_index"] == 1
    }
    traces = {
        (t["case_id"]): t
        for t in _load_jsonl(Q4 / "traces.jsonl")
        if t["system_name"] == RULE and t["run_index"] == 1
    }
    gold = {c["case_id"]: c for c in _load_jsonl(TEST_GOLD)}
    out = []
    for cid in _PICKS:
        r, t, g = results[cid], traces[cid], gold[cid]
        out.append(
            {
                "case_id": cid,
                "query": g["query"],
                "user_role": g["user_role"],
                "authorized": r["authorized"],
                "gold_action": r["gold_action"],
                "read": {
                    "retrieved": len(t.get("retrieved_chunk_ids") or []),
                    "surviving": len(t.get("surviving_chunk_ids") or []),
                    "blocked": len(t.get("blocked_chunk_ids") or []),
                    "citations": (t.get("sink_record") or {}).get("evidence_citations", [])[:3],
                },
                "detect": {
                    "conditions": r.get("detected_conditions") or [],
                    "authorized_actor": r.get("authorized_actor"),
                    "evidence_decision": r.get("evidence_decision"),
                },
                "act": {
                    "proposed_action": r["proposed_action"],
                    "controller_source": r.get("controller_source"),
                    "risk_tier": r.get("risk_tier"),
                },
                "govern": {
                    "validator_ok": r.get("validator_ok"),
                    "forced_action": r.get("forced_action"),
                    "approval_state": r.get("approval_state"),
                    "executed_side_effect": r.get("executed_side_effect"),
                    "sink_record_id": r.get("sink_record_id"),
                },
                "correct": r["proposed_action"] == r["gold_action"],
            }
        )
    return out


def build_audit() -> dict:
    traces = [
        t
        for t in _load_jsonl(Q4 / "traces.jsonl")
        if t["system_name"] == RULE and t["run_index"] == 1
    ]
    records, seen = [], set()
    for t in traces:
        rec = t.get("sink_record")
        if not rec or rec["record_id"] in seen:
            continue
        seen.add(rec["record_id"])
        records.append(
            {
                k: rec.get(k)
                for k in [
                    "record_id",
                    "action",
                    "condition",
                    "approval_state",
                    "actor_role",
                    "doc_ids",
                    "created_at",
                ]
            }
        )
    records.sort(key=lambda r: (r.get("created_at") or "", r["record_id"]))
    blocked = [r for r in records if r["approval_state"] == "escalated"]
    return {"run_id": "q4-p5-selection-calibrated", "records": records, "blocked": blocked}


def build_arc() -> list[dict]:
    return [
        {
            "q": "Q1",
            "tag": "v0.3-q1-hard-demo",
            "title": "可信 RAG + 反自欺评测",
            "metrics": [
                ["假回答率", "0.00"],
                ["引用结构有效性", "1.00"],
                ["污染 raw→grounded", "0.20→0.00"],
            ],
            "negative": "诚实代价：grounded 0.24 / false-refusal 0.46",
            "codes": ["F1", "F2", "F6"],
        },
        {
            "q": "Q2",
            "tag": "v1.0-q2-agentic-eval",
            "title": "类型化动作 agent + 评测治理",
            "metrics": [
                ["gated vs agentic", "0.227 vs 0.273"],
                ["rule == llm", "✓"],
                ["注入红队 strict", "1/10"],
            ],
            "negative": "诚实证伪：检索恢复 agent 无可证增益；判官不可部署，据实不上线",
            "codes": ["F4", "F5", "F9"],
        },
        {
            "q": "Q3",
            "tag": "v2.0-q3-action-governance",
            "title": "信任层从答案 → 动作",
            "metrics": [["越权动作拦截", "1.00"], ["F11 / F13", "0 / 0"], ["误动作率", "0.00"]],
            "negative": "诚实记录：动作选择中等，anti-gaming triad = False（门正确拒绝冒充）",
            "codes": ["F10", "F11", "F12", "F13"],
        },
        {
            "q": "Q4",
            "tag": "v3.0-q4-reliability",
            "title": "把负结果修成正结果 + 标准可观测",
            "metrics": [
                ["triad 留出集", "False → True"],
                ["precision@authorized", "0.45 → 0.65"],
                ["阈值 / validator", "冻结 / 零改"],
            ],
            "negative": "诚实定语：真但薄（过 ~1 case）；6/17 残留是小语料检索边界；"
            "两次 run 全披露",
            "codes": ["F10", "F12"],
        },
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "triad.json").write_text(
        json.dumps(build_triad(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "trajectories.json").write_text(
        json.dumps(build_trajectories(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "audit.json").write_text(
        json.dumps(build_audit(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "arc.json").write_text(
        json.dumps(build_arc(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote", sorted(p.name for p in OUT.glob("*.json")))


if __name__ == "__main__":
    main()
