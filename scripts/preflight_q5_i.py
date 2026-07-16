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

from app.eval.q5_claim_readiness import (
    evaluate_q5_claim_readiness,
    verify_q5_claim_readiness,
)
from app.eval.q5_provenance import q5_read_json
from app.eval.q5_symbolic_control import verify_q5_strong_symbolic_artifacts
from app.eval.q5_value_ledger import verify_q5_value_ledger
from scripts.preflight_q5_real import main as run_base_preflight

Q5_REAL_PREFLIGHT_I_SCHEMA = "q5-real-preflight-ir"


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
    verify_q5_i_preflight_payload(
        payload,
        run_summary=q5_read_json(args.mock_run / "summary.json"),
        value_summary=value,
        symbolic_summary=symbolic,
    )
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return payload


def verify_q5_i_preflight_payload(
    payload: dict[str, object],
    *,
    run_summary: dict[str, object],
    value_summary: dict[str, object],
    symbolic_summary: dict[str, object],
) -> dict[str, object]:
    """Recompute IR claim fields and reject a self-reported valid receipt."""

    if payload.get("schema_version") != Q5_REAL_PREFLIGHT_I_SCHEMA:
        raise ValueError("Q5 IR preflight schema is invalid")
    frontier = payload.get("value_frontier")
    if not isinstance(frontier, dict):
        raise ValueError("Q5 IR preflight value frontier is missing")
    if frontier.get("value_ledger") != value_summary:
        raise ValueError("Q5 IR preflight value sidecar summary mismatch")
    if frontier.get("strong_symbolic_control") != symbolic_summary:
        raise ValueError("Q5 IR preflight symbolic sidecar summary mismatch")
    claimed = frontier.get("claim_readiness")
    if not isinstance(claimed, dict):
        raise ValueError("Q5 IR preflight claim readiness is missing")
    readiness = verify_q5_claim_readiness(
        run_summary,
        value_summary,
        symbolic_summary,
        claimed,
    )
    expected_claim_errors = [
        f"claim readiness blocked: {blocker}" for blocker in readiness["blockers"]
    ]
    errors = payload.get("errors")
    if not isinstance(errors, list) or any(not isinstance(item, str) for item in errors):
        raise ValueError("Q5 IR preflight error ledger is invalid")
    actual_claim_errors = [
        item for item in errors if item.startswith("claim readiness blocked: ")
    ]
    if actual_claim_errors != expected_claim_errors:
        raise ValueError("Q5 IR preflight claim blocker ledger mismatch")
    if payload.get("valid") != (not errors):
        raise ValueError("Q5 IR preflight validity is not error-ledger-derived")
    request_policy = payload.get("request_policy")
    if not isinstance(request_policy, dict) or any(
        request_policy.get(field) != 0
        for field in (
            "completion_requests_sent_during_preflight",
            "http_model_requests_sent_during_preflight",
            "provider_model_calls_during_preflight",
        )
    ):
        raise ValueError("Q5 IR preflight request ledger is not zero")
    return payload


def verify_q5_i_preflight_receipt(
    receipt_path: Path | str,
    *,
    mock_run: Path | str,
    gold_path: Path | str,
    value_dir: Path | str,
    symbolic_dir: Path | str,
    dataset_root: Path | str = Path("data/q5/dev"),
) -> dict[str, object]:
    """Verify a written receipt through both sidecar verifiers and claim replay."""

    root = Path(dataset_root)
    run = Path(mock_run)
    value = verify_q5_value_ledger(run, gold_path, value_dir)
    symbolic = verify_q5_strong_symbolic_artifacts(
        tasks_path=root / "tasks.jsonl",
        environment_path=root / "environment.jsonl",
        runtime_cases_path=root / "runtime_cases.jsonl",
        gold_path=gold_path,
        output_dir=symbolic_dir,
    )
    payload = q5_read_json(Path(receipt_path))
    return verify_q5_i_preflight_payload(
        payload,
        run_summary=q5_read_json(run / "summary.json"),
        value_summary=value,
        symbolic_summary=symbolic,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
