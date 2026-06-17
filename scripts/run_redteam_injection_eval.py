# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.redteam import run_redteam_paired_eval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run paired clean-vs-poisoned indirect prompt injection eval."
    )
    parser.add_argument("--system", default="final_gated_calibrated")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--clean-chunks", type=Path, default=Path("data/generated/chunks.jsonl"))
    parser.add_argument(
        "--poisoned-chunks",
        type=Path,
        default=Path("data/generated/redteam/chunks.jsonl"),
    )
    parser.add_argument("--embedding-provider", default=None)
    parser.add_argument("--trust-gate-policy", default="legacy")
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-report", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = run_redteam_paired_eval(
            system_name=args.system,
            output_root=args.output_root,
            run_id=args.run_id,
            clean_chunks_path=args.clean_chunks,
            poisoned_chunks_path=args.poisoned_chunks,
            embedding_provider=args.embedding_provider,
            trust_gate_policy=args.trust_gate_policy,
            max_output_tokens=args.max_output_tokens,
            case_id=args.case_id,
            limit=args.limit,
            write_report=not args.no_report,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
