# ruff: noqa: E402
"""Generate a zero-completion-request receipt for one controlled Q5 real-dev run."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_dataset import load_q5_tasks
from app.eval.q5_pre_run import check_q5_pre_run
from app.eval.q5_provenance import (
    canonical_q5_model_family,
    derive_q5_model_identity,
    q5_read_jsonl,
    verify_q5_graded_run,
)
from app.eval.run_manifest import git_commit_sha
from app.llm.llm_client import get_llm_client

DEEPSEEK_INPUT_CACHE_MISS_USD_PER_MILLION = 0.14
DEEPSEEK_OUTPUT_USD_PER_MILLION = 0.28
INPUT_TOKEN_RESERVATION_PER_CALL = 8_192
REAL_DEV_COST_CAP_USD = 0.20
MAX_Q5_POLICY_STEPS = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("data/q5/dev"))
    parser.add_argument("--mock-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--real-output-root", type=Path, default=Path("data/eval_runs"))
    parser.add_argument("--real-run-id", required=True)
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--thinking-mode", choices=("disabled",), default="disabled")
    parser.add_argument("--k", type=int, choices=(1,), default=1)
    parser.add_argument("--seed", type=int, default=20260711)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--tls-timeout-seconds", type=float, default=10.0)
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    errors: list[str] = []
    commit = git_commit_sha()
    worktree_clean = _worktree_clean()
    if not worktree_clean:
        errors.append("worktree is not clean")
    if (Path("data/q5") / "test").exists():
        errors.append("formal q5_test exists and is forbidden in Batch 5-B")
    if args.provider != "deepseek" or args.model != "deepseek-v4-flash":
        errors.append("Batch 5-B primary identity must be deepseek/deepseek-v4-flash")
    if args.temperature != 0.0 or args.thinking_mode != "disabled":
        errors.append("controlled Q5 primary requires temperature=0 and thinking=disabled")
    if args.max_output_tokens != 512 or args.timeout_seconds != 30.0:
        errors.append("controlled Q5 primary requires max_output_tokens=512 and timeout=30")

    pre_run = check_q5_pre_run(args.dataset_root, dataset_partition="dev")
    if not pre_run.valid:
        errors.extend(f"dataset pre-run: {message}" for message in pre_run.errors)
    tasks = load_q5_tasks(args.dataset_root / "tasks.jsonl")
    if len(tasks) != 36:
        errors.append(f"q5_dev must contain 36 tasks, got {len(tasks)}")

    verified_mock = verify_q5_graded_run(
        args.mock_run,
        args.dataset_root / "gold.jsonl",
    )
    if verified_mock.git_commit_sha != commit:
        errors.append(
            "mock topology forecast is not anchored to the current commit: "
            f"mock={verified_mock.git_commit_sha} current={commit}"
        )
    mock_rows = [
        row
        for row in q5_read_jsonl(args.mock_run / "results.jsonl")
        if int(row.get("run_index") or 0) == 1
    ]
    expected_trials = len(tasks) * 3 * args.k
    if len(mock_rows) != expected_trials:
        errors.append(
            f"mock topology must contain {expected_trials} k=1 rows, got {len(mock_rows)}"
        )
    by_system = Counter()
    model_called_trials = Counter()
    for row in mock_rows:
        system = str(row.get("system") or "")
        by_system[system] += int(row.get("llm_calls") or 0)
        if int(row.get("llm_calls") or 0) > 0:
            model_called_trials[system] += 1
    expected_calls = sum(by_system.values())
    hard_call_limit = sum(model_called_trials.values()) * MAX_Q5_POLICY_STEPS

    client = get_llm_client(
        args.provider,
        model_name=args.model,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        timeout=args.timeout_seconds,
        thinking_mode=args.thinking_mode,
        purpose="q5_policy",
    )
    identity = derive_q5_model_identity(client)
    if (
        identity.identity_kind != "trusted_real_client"
        or identity.mock_instance
        or not identity.trusted_real_client
    ):
        errors.append("primary client did not attest as trusted real")
    if canonical_q5_model_family(identity) != "deepseek":
        errors.append("primary client did not resolve to the DeepSeek family")
    calls_before = int(getattr(client, "call_count", -1))
    tls = _tls_readiness(identity.base_url_host or "", args.tls_timeout_seconds)
    calls_after = int(getattr(client, "call_count", -1))
    if calls_before != 0 or calls_after != 0:
        errors.append("preflight unexpectedly changed provider model call_count")
    if not tls["ready"]:
        errors.append(f"provider TLS readiness failed: {tls['error']}")

    expected_budget = _budget(expected_calls, args.max_output_tokens)
    hard_budget = _budget(hard_call_limit, args.max_output_tokens)
    if hard_budget["cache_miss_cost_upper_usd"] > REAL_DEV_COST_CAP_USD:
        errors.append("hard cost reservation exceeds the frozen real-dev cost cap")
    command = _real_command(args)
    if "--gold" in command or "q5/test" in command or "q5\\test" in command:
        errors.append("planned runtime command crosses the task/gold or dev/test boundary")

    payload: dict[str, object] = {
        "schema_version": "q5-real-preflight-v1",
        "valid": not errors,
        "request_policy": {
            "completion_requests_sent_during_preflight": 0,
            "http_model_requests_sent_during_preflight": 0,
            "tls_handshake_only": True,
        },
        "freeze": {
            "git_commit_sha": commit,
            "worktree_clean": worktree_clean,
            "q5_test_absent": not (Path("data/q5") / "test").exists(),
            "post_run_mutation_forbidden": [
                "tasks",
                "runtime_cases",
                "environment",
                "gold",
                "gate_thresholds",
            ],
        },
        "dataset": {
            "partition": "dev",
            "case_count": len(tasks),
            "systems": [
                "q5_rule_agent",
                "q5_llm_agent",
                "q5_hybrid_agent",
            ],
            "k": args.k,
            "expected_trial_count": expected_trials,
            "sha256": pre_run.sha256,
            "mock_topology_run": verified_mock.run_id,
            "mock_topology_manifest_sha256": verified_mock.raw_manifest_sha256,
        },
        "primary": {
            "provider": identity.provider,
            "canonical_family": canonical_q5_model_family(identity),
            "model_id": identity.model_name,
            "model_version": "DeepSeek-V4-Flash",
            "provider_release": "2026-04-24",
            "instance_type": identity.instance_type,
            "identity_kind": identity.identity_kind,
            "identity_sha256": identity.identity_sha256,
            "base_url_host": identity.base_url_host,
            "temperature": args.temperature,
            "max_output_tokens": args.max_output_tokens,
            "timeout_seconds": args.timeout_seconds,
            "thinking_mode": args.thinking_mode,
            "automatic_retries": 0,
            "max_attempts_per_policy_step": 1,
            "fallback": "none",
            "model_or_parse_error_terminal": "safe_escalation",
            "mock_fallback_allowed": False,
            "rule_fallback_allowed": False,
        },
        "api_readiness": {
            "api_key_present": True,
            "client_constructible": True,
            "client_call_count_before": calls_before,
            "client_call_count_after": calls_after,
            "tls": tls,
            "model_id_officially_documented": True,
        },
        "forecast": {
            "expected_calls_by_system": dict(sorted(by_system.items())),
            "expected_model_called_trials_by_system": dict(
                sorted(model_called_trials.items())
            ),
            "expected_total_calls": expected_calls,
            "hard_call_limit": hard_call_limit,
            "expected_budget": expected_budget,
            "hard_budget": hard_budget,
            "authorized_cost_cap_usd": REAL_DEV_COST_CAP_USD,
            "pricing_usd_per_million_tokens": {
                "input_cache_miss": DEEPSEEK_INPUT_CACHE_MISS_USD_PER_MILLION,
                "output": DEEPSEEK_OUTPUT_USD_PER_MILLION,
            },
            "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing",
            "token_reservation_note": (
                "Input reservation is 8192 tokens per call, above the frozen q5_dev "
                "prompt surface; output is capped by max_tokens=512."
            ),
        },
        "planned_command": command,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(1)
    return payload


def _budget(call_count: int, max_output_tokens: int) -> dict[str, int | float]:
    input_tokens = call_count * INPUT_TOKEN_RESERVATION_PER_CALL
    output_tokens = call_count * max_output_tokens
    cost = (
        input_tokens * DEEPSEEK_INPUT_CACHE_MISS_USD_PER_MILLION
        + output_tokens * DEEPSEEK_OUTPUT_USD_PER_MILLION
    ) / 1_000_000
    return {
        "call_count": call_count,
        "input_token_upper": input_tokens,
        "output_token_upper": output_tokens,
        "total_token_upper": input_tokens + output_tokens,
        "cache_miss_cost_upper_usd": round(cost, 6),
    }


def _real_command(args: argparse.Namespace) -> str:
    parts = [
        ".venv\\Scripts\\python.exe",
        "scripts/run_q5_tasks.py",
        "--tasks data/q5/dev/tasks.jsonl",
        "--environment data/q5/dev/environment.jsonl",
        "--runtime-cases data/q5/dev/runtime_cases.jsonl",
        f"--output-root {args.real_output_root.as_posix()}",
        f"--run-id {args.real_run_id}",
        "--mode real",
        "--model-role primary",
        f"--provider {args.provider}",
        f"--model {args.model}",
        f"--temperature {args.temperature:g}",
        f"--max-output-tokens {args.max_output_tokens}",
        f"--timeout-seconds {args.timeout_seconds:g}",
        f"--thinking-mode {args.thinking_mode}",
        f"--k {args.k}",
        f"--seed {args.seed}",
        f"--bootstrap-resamples {args.bootstrap_resamples}",
        "--systems q5_rule_agent q5_llm_agent q5_hybrid_agent",
    ]
    return " ".join(parts)


def _worktree_clean() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return not result.stdout.strip()


def _tls_readiness(host: str, timeout: float) -> dict[str, object]:
    if not host:
        return {"ready": False, "host": host, "error": "missing host"}
    try:
        addresses = sorted(
            {
                item[4][0]
                for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        )
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as secured:
                protocol = secured.version()
                cipher = secured.cipher()
        return {
            "ready": True,
            "host": host,
            "port": 443,
            "resolved_address_count": len(addresses),
            "tls_protocol": protocol,
            "cipher": cipher[0] if cipher else None,
            "error": None,
        }
    except (OSError, ssl.SSLError) as exc:
        return {
            "ready": False,
            "host": host,
            "port": 443,
            "error": type(exc).__name__,
        }


if __name__ == "__main__":  # pragma: no cover
    main()
