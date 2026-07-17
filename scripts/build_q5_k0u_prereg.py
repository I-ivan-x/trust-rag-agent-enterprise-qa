"""Build or verify K0U-B practical-frontier preregistration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.q5_frontier_k0u_prereg import (  # noqa: E402
    verify_k0u_preregistration,
    write_k0u_preregistration,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (
        write_k0u_preregistration(args.output_dir)
        if args.command == "build"
        else verify_k0u_preregistration(args.output_dir)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
