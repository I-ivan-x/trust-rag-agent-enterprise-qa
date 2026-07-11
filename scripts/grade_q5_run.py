# ruff: noqa: E402
"""Grade one Q5 run or compose a verified dual-model summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_runner import grade_q5_run
from app.eval.q5_summary import summarize_q5_model_roles


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Grade Q5 artifacts with gold kept outside runtime execution."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    grade = commands.add_parser("grade", help="Grade one completed raw run.")
    grade.add_argument("--run-dir", type=Path, required=True)
    grade.add_argument("--gold", type=Path, required=True)
    summarize = commands.add_parser(
        "summarize", help="Compose verified primary and confirmatory runs."
    )
    summarize.add_argument("--primary-run", type=Path, required=True)
    summarize.add_argument("--confirmatory-run", type=Path, required=True)
    summarize.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    if args.command == "grade":
        artifacts = grade_q5_run(args.run_dir, args.gold)
        payload: dict[str, object] = {
            "run_dir": artifacts.run_dir.as_posix(),
            "summary": artifacts.summary_path.as_posix(),
            "gates": artifacts.gates_path.as_posix(),
            "row_count": artifacts.row_count,
        }
    else:
        artifacts = summarize_q5_model_roles(
            args.primary_run,
            args.confirmatory_run,
            args.output_dir,
        )
        payload = {
            "output_dir": artifacts.output_dir.as_posix(),
            "summary": artifacts.summary_path.as_posix(),
            "gates": artifacts.gates_path.as_posix(),
            "ledger": artifacts.ledger_path.as_posix(),
        }
    print(json.dumps(payload, sort_keys=True))
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
