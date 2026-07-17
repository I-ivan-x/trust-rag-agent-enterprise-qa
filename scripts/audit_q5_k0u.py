"""Build or verify the K0U dual-layer deterministic audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.q5_frontier_k0u_audit import (  # noqa: E402
    verify_k0u_audit,
    write_k0u_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--require-commit-lineage", action="store_true")
    args = parser.parse_args()
    result = (
        write_k0u_audit(args.output_dir)
        if args.command == "build"
        else verify_k0u_audit(
            args.output_dir,
            require_commit_lineage=args.require_commit_lineage,
        )
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
