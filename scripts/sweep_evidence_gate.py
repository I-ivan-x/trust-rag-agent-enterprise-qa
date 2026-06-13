# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.core.enums import EvalSplit
from app.eval.dataset import write_jsonl
from app.eval.runner import run_eval
from app.guards.evidence_gate import EvidenceGateConfig

DEFAULT_CONFIG_SPECS = (
    "default:min_support_count=1,min_score=none",
    "support2:min_support_count=2,min_score=none",
    "score0:min_support_count=1,min_score=0",
    "support2_score0:min_support_count=2,min_score=0",
    "score1:min_support_count=1,min_score=1",
)
_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class SweepPoint:
    label: str
    config: EvidenceGateConfig


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Q2 Phase 1 evidence-gate calibration sweep."
    )
    parser.add_argument("--split", choices=[split.value for split in EvalSplit], required=True)
    parser.add_argument(
        "--systems",
        default="final_gated",
        help="Comma-separated final system names, default: final_gated.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock-run", action="store_true")
    mode.add_argument("--real-run", action="store_true")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--sweep-id", default=None)
    parser.add_argument("--limit", type=int, default=None, help="Cap number of cases.")
    parser.add_argument("--case-id", default=None, help="Run a single case id.")
    parser.add_argument("--max-cases", type=int, default=None, help="Alias cap for cases.")
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Delay between real LLM cases for rate-limit friendliness.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Override max output tokens for real LLM calls.",
    )
    parser.add_argument(
        "--trust-gate-policy",
        choices=["legacy", "neighbor_tolerant"],
        default=None,
        help="Override trust gate policy variant for every sweep point.",
    )
    parser.add_argument(
        "--config",
        action="append",
        dest="configs",
        default=None,
        help=(
            "Sweep point as label:min_support_count=N,min_score=FLOAT|none. "
            "Repeat to replace the default five-point sweep."
        ),
    )
    parser.add_argument(
        "--write-reports",
        action="store_true",
        help="Allow each child run to update docs/EVALUATION_REPORT.md and friends.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    summary = run_sweep(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary


def run_sweep(args: argparse.Namespace) -> dict[str, Any]:
    systems = _parse_systems(args.systems)
    points = _parse_sweep_points(args.configs or DEFAULT_CONFIG_SPECS)
    sweep_id = args.sweep_id or _make_sweep_id(args.split)
    sweep_root = args.output_root or (get_settings().eval_runs_dir / sweep_id)
    sweep_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    child_summaries: list[dict[str, Any]] = []
    for point in points:
        child_summary = run_eval(
            split=args.split,
            systems=systems,
            mock_run=args.mock_run,
            real_run=args.real_run,
            output_root=sweep_root,
            run_id=point.label,
            write_reports=args.write_reports,
            limit=args.limit,
            case_id=args.case_id,
            max_cases=args.max_cases,
            sleep_seconds=args.sleep_seconds,
            max_output_tokens=args.max_output_tokens,
            evidence_gate_config=point.config,
            trust_gate_policy=args.trust_gate_policy,
        )
        child_summaries.append(child_summary)
        rows.extend(_rows_for_child_summary(point, child_summary))

    summary = {
        "sweep_id": sweep_id,
        "split": args.split,
        "systems": systems,
        "mode": "real_run" if args.real_run else "mock_smoke",
        "trust_gate_policy": args.trust_gate_policy,
        "config_count": len(points),
        "configs": [
            {"label": point.label, **point.config.model_dump(mode="json")}
            for point in points
        ],
        "rows": rows,
        "child_run_ids": [summary["run_id"] for summary in child_summaries],
        "sweep_root": sweep_root.as_posix(),
    }
    (sweep_root / "sweep_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_jsonl(sweep_root / "sweep_results.jsonl", rows)
    return summary


def _parse_systems(raw: str) -> list[str]:
    systems = [item.strip() for item in raw.split(",") if item.strip()]
    if not systems:
        raise ValueError("--systems must include at least one system")
    return systems


def _parse_sweep_points(raw_specs: Sequence[str]) -> list[SweepPoint]:
    points = [_parse_sweep_point(raw) for raw in raw_specs]
    labels = [point.label for point in points]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise ValueError(f"Duplicate sweep labels: {', '.join(duplicates)}")
    return points


def _parse_sweep_point(raw: str) -> SweepPoint:
    if ":" not in raw:
        raise ValueError(
            "Sweep config must use label:min_support_count=N,min_score=FLOAT|none"
        )
    label, body = raw.split(":", 1)
    label = label.strip()
    if not label or not _LABEL_PATTERN.match(label):
        raise ValueError(f"Invalid sweep label: {label!r}")

    values: dict[str, str] = {}
    for item in body.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid config item: {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if key not in {"min_support_count", "min_score"}:
            raise ValueError(f"Unsupported evidence gate config key: {key}")
        values[key] = value.strip()

    min_support_count = int(values.get("min_support_count", "1"))
    min_score = _parse_optional_float(values.get("min_score", "none"))
    return SweepPoint(
        label=label,
        config=EvidenceGateConfig(
            min_support_count=min_support_count,
            min_score=min_score,
        ),
    )


def _parse_optional_float(raw: str) -> float | None:
    if raw.lower() in {"", "none", "null"}:
        return None
    return float(raw)


def _rows_for_child_summary(
    point: SweepPoint,
    child_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summary_metrics = child_summary.get("summary_metrics", {})
    for system_name, metrics in summary_metrics.items():
        rows.append(
            {
                "label": point.label,
                "run_id": child_summary["run_id"],
                "run_dir": child_summary["run_dir"],
                "system_name": system_name,
                "trust_gate_policy": child_summary.get("trust_gate_policy"),
                "min_support_count": point.config.min_support_count,
                "min_score": point.config.min_score,
                "cases": metrics.get("cases"),
                "false_refusal_rate": metrics.get("false_refusal_rate"),
                "false_answer_rate": metrics.get("false_answer_rate"),
                "grounded_correctness": metrics.get("grounded_correctness"),
                "refusal_rate": metrics.get("refusal_rate"),
                "raw_correctness": metrics.get("raw_correctness"),
                "citation_valid": metrics.get("citation_valid"),
                "llm_call_count": child_summary.get("llm_call_count"),
                "headline_eligible": child_summary.get("headline_eligible"),
                "pilot_eligible": child_summary.get("pilot_eligible"),
            }
        )
    return rows


def _make_sweep_id(split: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{split}-evidence-gate-sweep"


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
