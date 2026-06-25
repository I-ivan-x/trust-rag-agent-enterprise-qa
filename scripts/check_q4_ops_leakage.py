# ruff: noqa: E402
"""Q4-P2 leakage + gold-id validation for the ops dev/test split (SPEC_Q4_P2_P3 §1.2).

Checks the Q4 ops dev set (original 14 + 2 additions = 16) and the held-out ops test
set (20) *each* against the ops_runbook corpus, reusing the shared leakage internals.
A split passes when it has no blocking flags: no high title overlap (memorization),
no missing gold doc/chunk (dangling references), no answer-copy, and every seeded
overlay doc is covered by some gold case ("bidirectional").

This is P2 tooling, not P3/P4 calibration -- it is allowed to read the test file. The
calibration loop (run_q3_governance_ablation --split ops_dev / the unit tests) never
loads ops_test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.enums import EvalSplit
from app.eval.dataset import load_eval_cases
from scripts.check_eval_leakage import _check_cases, _chunks_from_corpus

OPS_CORPUS_DIR = Path("data/ops_runbook_corpus")
OPS_OVERLAY_PATH = OPS_CORPUS_DIR / "overlay" / "metadata_overlay.yaml"
REPORT_DIR = Path("data/eval_runs")

SPLITS = {
    "ops_dev": EvalSplit.ops_dev,
    "ops_test": EvalSplit.ops_test,
}


def main() -> int:
    chunks = _chunks_from_corpus(OPS_CORPUS_DIR, overlay_path=OPS_OVERLAY_PATH)
    all_passed = True
    for name, split in SPLITS.items():
        cases = load_eval_cases(split)
        report = _check_cases(cases, chunks)
        report["split"] = name
        passed = not report["blocking_flags"]
        all_passed = all_passed and passed
        out = REPORT_DIR / f"ops_runbook_action_v1_{name}_leakage_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        missing_gold = [f for f in report["flags"] if f["flag_type"].startswith("missing_gold")]
        print(
            f"[{name}] cases={report['case_count']} passed={passed} "
            f"flags={len(report['flags'])} blocking={len(report['blocking_flags'])} "
            f"missing_gold={len(missing_gold)} -> {out.as_posix()}"
        )
        for flag in report["blocking_flags"]:
            print(f"    BLOCKING {flag['case_id']}: {flag['flag_type']} ({flag['score']})")

    print("ALL_PASSED" if all_passed else "FAILED")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
