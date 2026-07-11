# ruff: noqa: E402
"""Validate a formal Q5 dataset before any policy-model execution."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_pre_run import check_q5_pre_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/q5/dev"))
    parser.add_argument("--partition", choices=("dev", "test"), default="dev")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    report = check_q5_pre_run(args.root, dataset_partition=args.partition)
    payload = report.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    if not report.valid:
        raise SystemExit(1)
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
