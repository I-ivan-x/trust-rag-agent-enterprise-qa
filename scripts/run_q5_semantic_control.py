# ruff: noqa: E402
"""Run the isolated Q5 fixed-table solvability diagnostic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_dataset import load_q5_gold, load_q5_runtime_dataset
from app.eval.q5_runner import load_q5_runtime_cases
from app.eval.q5_semantic_control import (
    execute_q5_semantic_table_rule_control,
    grade_q5_semantic_table_rule_control,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--runtime-cases", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--k", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    dataset = load_q5_runtime_dataset(args.tasks, args.environment)
    execution = execute_q5_semantic_table_rule_control(
        dataset.tasks,
        dataset.environment,
        load_q5_runtime_cases(args.runtime_cases),
        k=args.k,
    )
    report = grade_q5_semantic_table_rule_control(
        execution,
        load_q5_gold(args.gold),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload = {
        "output": args.output.as_posix(),
        "fixed_table_solvability": report.fixed_table_solvability,
        "external_requests": 0,
    }
    print(json.dumps(payload, sort_keys=True))
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
