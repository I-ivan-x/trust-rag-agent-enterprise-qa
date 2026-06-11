# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.enums import EvalSplit
from app.eval.runner import run_eval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Week 5B local eval.")
    parser.add_argument("--split", choices=[split.value for split in EvalSplit], required=True)
    parser.add_argument("--systems", required=True, help="Comma-separated system names.")
    parser.add_argument("--mock-run", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--real-run", action="store_true")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    systems = [item.strip() for item in args.systems.split(",") if item.strip()]
    try:
        summary = run_eval(
            split=args.split,
            systems=systems,
            mock_run=args.mock_run,
            retrieval_only=args.retrieval_only,
            real_run=args.real_run,
            output_root=args.output_root,
            run_id=args.run_id,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

