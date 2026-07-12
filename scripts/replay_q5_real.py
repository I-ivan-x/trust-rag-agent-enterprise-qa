# ruff: noqa: E402
"""Verify and replay one Q5 graded run into an independent diagnostic directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_replay import replay_q5_graded_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fixed-table-solvability", type=float)
    parser.add_argument("--require-batch5d-signature", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    report = replay_q5_graded_run(
        args.run_dir,
        args.gold,
        args.output_dir,
        fixed_table_solvability=args.fixed_table_solvability,
        require_batch5d_signature=args.require_batch5d_signature,
    )
    payload = {
        "output_dir": args.output_dir.as_posix(),
        "calls_only_upper_bound_ratio": report["calls_only_upper_bound_ratio"],
        "external_requests": 0,
    }
    print(json.dumps(payload, sort_keys=True))
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
