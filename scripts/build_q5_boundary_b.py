"""Build or verify the hash-closed Q5 Boundary B package."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_boundary_b import verify_boundary_b, write_boundary_b  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/eval_runs/q5-boundary-b-k0s"),
    )
    parser.add_argument("--dev-v2-dir", type=Path, default=Path("data/q5_frontier/dev-v2"))
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    kwargs = {"dev_v2_dir": args.dev_v2_dir}
    result = (
        write_boundary_b(args.output_dir, **kwargs)
        if args.command == "build"
        else verify_boundary_b(args.output_dir, **kwargs)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


if __name__ == "__main__":  # pragma: no cover
    main()
