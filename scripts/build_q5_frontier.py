"""Build or verify the isolated Q5 v5 capability-frontier dev namespace."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_frontier import (  # noqa: E402
    verify_frontier_artifacts,
    write_frontier_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/q5_frontier/dev")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        payload = write_frontier_artifacts(args.output_dir)
    else:
        payload = verify_frontier_artifacts(args.output_dir)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
