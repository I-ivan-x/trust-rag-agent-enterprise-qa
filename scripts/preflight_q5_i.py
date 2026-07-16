# ruff: noqa: E402
"""Enrich zero-request Q5 preflight with value-frontier claim readiness."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_claim_readiness import evaluate_q5_claim_readiness
from app.eval.q5_provenance import q5_read_json
from app.eval.q5_symbolic_control import verify_q5_strong_symbolic_artifacts
from app.eval.q5_value_ledger import verify_q5_value_ledger
from scripts.preflight_q5_real import main as run_base_preflight

Q5_REAL_PREFLIGHT_I_SCHEMA = "q5-real-preflight-i"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("data/q5/dev"))
    parser.add_argument("--mock-run", type=Path, required=True)
    parser.add_argument("--value-dir", type=Path, required=True)
    parser.add_argument("--symbolic-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--real-output-root", type=Path, default=Path("data/eval_runs"))
    parser.add_argument("--real-run-id", required=True)
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--thinking-mode", choices=("disabled",), default="disabled")
    parser.add_argument("--k", type=int, choices=(3,), default=3)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--tls-timeout-seconds", type=float, default=10.0)
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    base_args = [
        "--dataset-root",
        str(args.dataset_root),
        "--mock-run",
        str(args.mock_run),
        "--output",
        str(args.output),
        "--real-output-root",
        str(args.real_output_root),
        "--real-run-id",
        args.real_run_id,
        "--provider",
        args.provider,
        "--model",
        args.model,
        "--temperature",
        str(args.temperature),
        "--max-output-tokens",
        str(args.max_output_tokens),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--thinking-mode",
        args.thinking_mode,
        "--k",
        str(args.k),
        "--seed",
        str(args.seed),
        "--bootstrap-resamples",
        str(args.bootstrap_resamples),
        "--tls-timeout-seconds",
        str(args.tls_timeout_seconds),
    ]
    payload = run_base_preflight(base_args)
    value = verify_q5_value_ledger(
        args.mock_run,
        args.dataset_root / "gold.jsonl",
        args.value_dir,
    )
    symbolic = verify_q5_strong_symbolic_artifacts(
        tasks_path=args.dataset_root / "tasks.jsonl",
        environment_path=args.dataset_root / "environment.jsonl",
        runtime_cases_path=args.dataset_root / "runtime_cases.jsonl",
        gold_path=args.dataset_root / "gold.jsonl",
        output_dir=args.symbolic_dir,
    )
    readiness = evaluate_q5_claim_readiness(
        q5_read_json(args.mock_run / "summary.json"),
        value,
        symbolic,
    )
    payload["schema_version"] = Q5_REAL_PREFLIGHT_I_SCHEMA
    payload["value_frontier"] = {
        "value_ledger": value,
        "strong_symbolic_control": symbolic,
        "claim_readiness": readiness,
    }
    if not readiness["valid"]:
        payload["valid"] = False
        payload["errors"] = list(payload.get("errors") or []) + [
            f"claim readiness blocked: {blocker}"
            for blocker in readiness["blockers"]
        ]
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
