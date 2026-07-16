# ruff: noqa: E402
"""Build or verify the hash-closed Q5 strong symbolic control."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_symbolic_control import (
    build_q5_strong_symbolic_artifacts,
    verify_q5_strong_symbolic_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--runtime-cases", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    function = (
        build_q5_strong_symbolic_artifacts
        if args.command == "build"
        else verify_q5_strong_symbolic_artifacts
    )
    result = function(
        tasks_path=args.tasks,
        environment_path=args.environment,
        runtime_cases_path=args.runtime_cases,
        gold_path=args.gold,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":  # pragma: no cover
    main()
