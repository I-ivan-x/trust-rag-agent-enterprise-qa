# ruff: noqa: E402
"""Build or verify the offline Q5 value ledger."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_value_ledger import build_q5_value_ledger, verify_q5_value_ledger


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--value-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        payload = build_q5_value_ledger(args.run_dir, args.gold, args.value_dir)
    else:
        payload = verify_q5_value_ledger(args.run_dir, args.gold, args.value_dir)
    print(json.dumps(payload, sort_keys=True))
    return payload


if __name__ == "__main__":
    main()
