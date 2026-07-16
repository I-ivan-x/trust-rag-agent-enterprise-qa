"""Build or verify the hash-closed Q5 Boundary A evidence package."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_boundary_a import (  # noqa: E402
    verify_boundary_a_evidence,
    write_boundary_a_evidence,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--v3-run",
        type=Path,
        default=Path(
            "data/eval_runs/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3"
        ),
    )
    parser.add_argument(
        "--v3-gold", type=Path, default=Path("data/q5/archive/dev-v3/gold.jsonl")
    )
    parser.add_argument(
        "--v4-run",
        type=Path,
        default=Path("data/eval_runs/q5-dev-v4-mock-ir-7a9bf34-primary-k3"),
    )
    parser.add_argument(
        "--v4-gold", type=Path, default=Path("data/q5/dev/gold.jsonl")
    )
    parser.add_argument(
        "--value-dir",
        type=Path,
        default=Path("data/eval_runs/q5-dev-v4-value-ir-7a9bf34-primary-k3"),
    )
    parser.add_argument(
        "--symbolic-dir",
        type=Path,
        default=Path("data/eval_runs/q5-dev-v4-symbolic-ir-7a9bf34-primary-k3"),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path(
            "data/eval_runs/q5-dev-v4-preflight-ir-7a9bf34-primary-k3.json"
        ),
    )
    parser.add_argument(
        "--dataset-root", type=Path, default=Path("data/q5/dev")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    kwargs = {
        "v3_run": args.v3_run,
        "v3_gold": args.v3_gold,
        "v4_run": args.v4_run,
        "v4_gold": args.v4_gold,
        "value_dir": args.value_dir,
        "symbolic_dir": args.symbolic_dir,
        "receipt_path": args.receipt,
        "dataset_root": args.dataset_root,
    }
    if args.command == "build":
        payload = write_boundary_a_evidence(args.output_dir, **kwargs)
    else:
        payload = verify_boundary_a_evidence(args.output_dir, **kwargs)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
