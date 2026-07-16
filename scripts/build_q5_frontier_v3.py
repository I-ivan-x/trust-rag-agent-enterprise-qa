"""Build or verify the isolated Q5 K0S frontier v3 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_frontier_v3 import (  # noqa: E402
    verify_frontier_v3_artifacts,
    write_frontier_v3_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/q5_frontier/dev-v3"))
    parser.add_argument(
        "--compiler-fixtures",
        type=Path,
        default=Path("tests/fixtures/q5_frontier_v3/compiler_gold.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    kwargs = {"compiler_fixture_path": args.compiler_fixtures}
    result = (
        write_frontier_v3_artifacts(args.output_dir, **kwargs)
        if args.command == "build"
        else verify_frontier_v3_artifacts(args.output_dir, **kwargs)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


if __name__ == "__main__":  # pragma: no cover
    main()
