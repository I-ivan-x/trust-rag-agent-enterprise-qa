# ruff: noqa: E402

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

DEFAULT_BASELINE_PATH = Path("data/eval_baselines/regression_baseline_v1.json")
DEFAULT_EVAL_RUNS_DIR = Path("data/eval_runs")
ALLOWED_DIRECTIONS = {">=", "==", "<="}


@dataclass(frozen=True)
class RegressionCheck:
    status: str
    run_id: str
    split: str
    mode: str
    system: str
    metric: str
    actual_value: float | None
    baseline_value: float
    direction: str
    tolerance: float
    source_run_id: str
    note: str

    @property
    def failed(self) -> bool:
        return self.status == "REGRESSION"


def load_baseline(path: Path = DEFAULT_BASELINE_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("Baseline must be a JSON list or an object with an entries list.")
    for index, entry in enumerate(entries, 1):
        _validate_baseline_entry(entry, index)
    return entries


def load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Summary must be a JSON object: {path}")
    return payload


def resolve_summary_path(identifier: str, eval_runs_dir: Path = DEFAULT_EVAL_RUNS_DIR) -> Path:
    direct = Path(identifier)
    if direct.is_file():
        return direct
    if direct.is_dir() and (direct / "summary.json").is_file():
        return direct / "summary.json"

    run_path = eval_runs_dir / identifier / "summary.json"
    if run_path.is_file():
        return run_path
    raise FileNotFoundError(
        f"Could not resolve summary path or run_id: {identifier}. Checked {direct} and {run_path}."
    )


def check_regressions(
    baseline_entries: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> list[RegressionCheck]:
    checks: list[RegressionCheck] = []
    for summary in summaries:
        for entry in baseline_entries:
            if not _entry_matches_summary(entry, summary):
                continue
            checks.append(_check_entry(entry, summary))
    return checks


def format_checks(checks: list[RegressionCheck]) -> str:
    if not checks:
        return "No baseline entries matched the provided summaries.\n"

    headers = [
        "status",
        "run_id",
        "system",
        "metric",
        "actual",
        "rule",
        "source",
    ]
    rows = []
    for check in checks:
        rows.append(
            [
                check.status,
                check.run_id,
                check.system,
                check.metric,
                _format_value(check.actual_value),
                f"{check.direction} {check.baseline_value:g} tol {check.tolerance:g}",
                check.source_run_id,
            ]
        )
    widths = [
        max(len(str(row[index])) for row in [headers, *rows]) for index in range(len(headers))
    ]
    lines = [
        " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        " | ".join("-" * width for width in widths),
    ]
    lines.extend(
        " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    baseline_entries = load_baseline(args.baseline)
    summaries = [
        load_summary(resolve_summary_path(identifier, args.eval_runs_dir))
        for identifier in args.summaries
    ]
    checks = check_regressions(baseline_entries, summaries)
    print(format_checks(checks), end="")
    if not checks:
        return 2
    failed = [check for check in checks if check.failed]
    if failed:
        print(f"\nRegression gate failed: {len(failed)} metric(s) regressed.")
        return 1
    print(f"\nRegression gate passed: {len(checks)} metric(s) checked.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare existing eval run summary.json files against frozen regression "
            "baselines. This script only reads summaries; it never reruns eval or calls an LLM."
        )
    )
    parser.add_argument(
        "summaries",
        nargs="+",
        help="summary.json path, run directory, or run_id under data/eval_runs.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help=f"Baseline JSON path (default: {DEFAULT_BASELINE_PATH}).",
    )
    parser.add_argument(
        "--eval-runs-dir",
        type=Path,
        default=DEFAULT_EVAL_RUNS_DIR,
        help=f"Directory used to resolve run_id inputs (default: {DEFAULT_EVAL_RUNS_DIR}).",
    )
    return parser.parse_args(argv)


def _validate_baseline_entry(entry: dict[str, Any], index: int) -> None:
    required = {
        "metric",
        "baseline_value",
        "direction",
        "tolerance",
        "source_run_id",
        "note",
        "split",
        "system",
    }
    missing = sorted(required - set(entry))
    if missing:
        raise ValueError(f"Baseline entry #{index} is missing fields: {missing}")
    if entry["direction"] not in ALLOWED_DIRECTIONS:
        raise ValueError(f"Baseline entry #{index} has unsupported direction: {entry['direction']}")
    _as_float(entry["baseline_value"], f"entry #{index} baseline_value")
    _as_float(entry["tolerance"], f"entry #{index} tolerance")


def _entry_matches_summary(entry: dict[str, Any], summary: dict[str, Any]) -> bool:
    split = summary.get("split") or summary.get("eval_split")
    if entry.get("split") != split:
        return False
    if entry.get("mode") and entry["mode"] != summary.get("mode"):
        return False
    system = entry["system"]
    metrics_by_system = summary.get("summary_metrics", {})
    if system not in metrics_by_system:
        return False
    return entry["metric"] in metrics_by_system[system]


def _check_entry(entry: dict[str, Any], summary: dict[str, Any]) -> RegressionCheck:
    system = entry["system"]
    metric = entry["metric"]
    actual_value = _as_float(
        summary["summary_metrics"][system][metric],
        f"{summary.get('run_id', 'unknown')}/{system}/{metric}",
    )
    baseline_value = _as_float(entry["baseline_value"], f"{system}/{metric} baseline")
    tolerance = _as_float(entry["tolerance"], f"{system}/{metric} tolerance")
    status = "PASS"
    note = str(entry.get("note", ""))

    required_num_cases = entry.get("required_num_cases")
    if required_num_cases is not None and summary.get("num_cases") != required_num_cases:
        status = "REGRESSION"
        note = f"num_cases mismatch: expected {required_num_cases}, got {summary.get('num_cases')}"
    elif entry.get("require_headline_eligible") and not summary.get("headline_eligible"):
        status = "REGRESSION"
        note = "headline_eligible is false for a gated baseline metric"
    elif _violates(actual_value, baseline_value, entry["direction"], tolerance):
        status = "REGRESSION"

    return RegressionCheck(
        status=status,
        run_id=str(summary.get("run_id", "unknown")),
        split=str(summary.get("split") or summary.get("eval_split") or "unknown"),
        mode=str(summary.get("mode", "unknown")),
        system=system,
        metric=metric,
        actual_value=actual_value,
        baseline_value=baseline_value,
        direction=entry["direction"],
        tolerance=tolerance,
        source_run_id=str(entry["source_run_id"]),
        note=note,
    )


def _violates(
    actual_value: float,
    baseline_value: float,
    direction: str,
    tolerance: float,
) -> bool:
    if direction == ">=":
        return actual_value < baseline_value - tolerance
    if direction == "<=":
        return actual_value > baseline_value + tolerance
    if direction == "==":
        return abs(actual_value - baseline_value) > tolerance
    raise ValueError(f"Unsupported direction: {direction}")


def _as_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"Expected numeric value for {label}, got {value!r}")


def _format_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


if __name__ == "__main__":
    raise SystemExit(main())
