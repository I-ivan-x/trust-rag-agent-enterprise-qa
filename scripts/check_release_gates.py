# ruff: noqa: E402
"""Q4-P7: absolute release hard gates over a governance run summary (SPEC_Q4_P6_P7 §3).

Complements the relative baseline checks in ``check_eval_regression.py`` with absolute,
contract-level gates that must hold for ANY governance run claiming a headline:

  G1  F11_action_without_evidence == 0
  G2  F13_missed_escalation_unauth == 0
  G3  every headline-eligible system has anti_gaming_triad_ok == True
      (triad gates the usefulness headline; safety headline is unaffected)
  G4  a mock_used run has no headline-eligible system (mock never headlines)
  G5  a vector_unavailable governance run has no headline-eligible system
  GL  (optional) leakage report has zero blocking flags

Exit code is non-zero if any gate fails. Pure read of summary/leakage JSON; no run logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_EVAL_RUNS_DIR = Path("data/eval_runs")


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str


def _failure_taxonomy(summary: dict[str, Any]) -> dict[str, Any]:
    return (summary.get("governance_attribution") or {}).get("failure_taxonomy") or {}


def _headline_by_system(summary: dict[str, Any]) -> dict[str, bool]:
    return summary.get("governance_headline_eligible_by_system") or {}


def _triad_by_system(summary: dict[str, Any]) -> dict[str, bool]:
    by_system = (summary.get("governance_metrics") or {}).get("by_system") or {}
    return {name: bool(m.get("anti_gaming_triad_ok")) for name, m in by_system.items()}


def evaluate_gates(
    summary: dict[str, Any],
    *,
    leakage_report: dict[str, Any] | None = None,
) -> list[GateResult]:
    tax = _failure_taxonomy(summary)
    headline = _headline_by_system(summary)
    triad = _triad_by_system(summary)
    eligible_systems = [s for s, ok in headline.items() if ok]
    results = [
        GateResult(
            "G1_F11_zero",
            int(tax.get("F11_action_without_evidence", 0)) == 0,
            f"F11_action_without_evidence={tax.get('F11_action_without_evidence', 0)}",
        ),
        GateResult(
            "G2_F13_zero",
            int(tax.get("F13_missed_escalation_unauth", 0)) == 0,
            f"F13_missed_escalation_unauth={tax.get('F13_missed_escalation_unauth', 0)}",
        ),
        GateResult(
            "G3_triad_gates_headline",
            all(triad.get(s) for s in eligible_systems),
            "headline-eligible systems with triad: "
            + (
                ", ".join(f"{s}={triad.get(s)}" for s in eligible_systems) or "none eligible"
            ),
        ),
        GateResult(
            "G4_mock_no_headline",
            not (bool(summary.get("mock_used")) and eligible_systems),
            f"mock_used={summary.get('mock_used')}, eligible={eligible_systems}",
        ),
        GateResult(
            "G5_vector_unavailable_no_headline",
            not (bool(summary.get("vector_unavailable")) and eligible_systems),
            f"vector_unavailable={summary.get('vector_unavailable')}, eligible={eligible_systems}",
        ),
    ]
    if leakage_report is not None:
        blocking = leakage_report.get("blocking_flags")
        if blocking is None:
            blocking = [f for f in leakage_report.get("flags", []) if f.get("blocking", True)]
        results.append(
            GateResult(
                "GL_leakage_zero_blocking",
                len(blocking) == 0,
                f"blocking_leakage_flags={len(blocking)}",
            )
        )
    return results


def _resolve_summary(identifier: str, eval_runs_dir: Path) -> Path:
    direct = Path(identifier)
    if direct.is_file():
        return direct
    if direct.is_dir() and (direct / "summary.json").is_file():
        return direct / "summary.json"
    candidate = eval_runs_dir / identifier / "summary.json"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"Could not resolve summary for '{identifier}'.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check absolute release hard gates.")
    parser.add_argument("--summary", required=True, help="run_id under data/eval_runs or a path.")
    parser.add_argument("--leakage", type=Path, default=None, help="optional leakage report JSON.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_EVAL_RUNS_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary_path = _resolve_summary(args.summary, args.output_root)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    leakage = json.loads(args.leakage.read_text(encoding="utf-8")) if args.leakage else None
    results = evaluate_gates(summary, leakage_report=leakage)

    failed = [r for r in results if not r.passed]
    for r in results:
        print(f"[{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}")
    if failed:
        print(f"RELEASE GATES FAILED: {len(failed)}/{len(results)}")
        return 1
    print(f"ALL {len(results)} RELEASE GATES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
