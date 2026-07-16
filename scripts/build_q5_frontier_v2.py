"""Build or verify the isolated Q5 K0R v2 frontier artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_frontier_v2 import (  # noqa: E402
    verify_frontier_v2_artifacts,
    write_frontier_v2_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/q5_frontier/dev-v2"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        result = write_frontier_v2_artifacts(args.output_dir)
    else:
        result = verify_frontier_v2_artifacts(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


if __name__ == "__main__":  # pragma: no cover
    main()
