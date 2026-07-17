"""Build or verify the versioned Boundary F addendum."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.q5_boundary_f_addendum import (  # noqa: E402
    verify_boundary_f_addendum,
    write_boundary_f_addendum,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (
        write_boundary_f_addendum(args.output_dir)
        if args.command == "build"
        else verify_boundary_f_addendum(args.output_dir)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
