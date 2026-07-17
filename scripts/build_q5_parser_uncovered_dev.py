"""Build or verify the post-preregistration parser-uncovered development package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_frontier_parser_uncovered_v4 import (  # noqa: E402
    verify_parser_uncovered_dev_v4,
    write_parser_uncovered_dev_v4,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--require-parent-commit", action="store_true")
    args = parser.parse_args()
    result = (
        write_parser_uncovered_dev_v4(args.output_dir)
        if args.command == "build"
        else verify_parser_uncovered_dev_v4(
            args.output_dir,
            require_parent_commit=args.require_parent_commit,
        )
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
