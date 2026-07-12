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
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_dataset import load_q5_tasks
from app.eval.q5_pre_run import check_q5_pre_run
from app.eval.q5_provenance import (
    canonical_q5_model_family,
    derive_q5_model_identity,
    q5_read_json,
    q5_read_jsonl,
    verify_q5_graded_run,
)
from app.eval.run_manifest import git_commit_sha
from app.llm.llm_client import get_llm_client

DEEPSEEK_INPUT_CACHE_MISS_USD_PER_MILLION = 0.14
DEEPSEEK_OUTPUT_USD_PER_MILLION = 0.28
INPUT_TOKEN_RESERVATION_PER_CALL = 8_192
MAX_Q5_POLICY_STEPS = 3
Q5_REAL_PREFLIGHT_SCHEMA = "q5-real-preflight-v2"
Q5_REAL_K = 3
Q5_REAL_CASE_COUNT = 36
Q5_REAL_SYSTEMS = (
    "q5_rule_agent",
    "q5_llm_agent",
    "q5_hybrid_agent",
)


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
    parser.add_argument("--k", type=int, choices=(Q5_REAL_K,), default=Q5_REAL_K)
    parser.add_argument("--seed", type=int, default=20260712)
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
        errors.append("formal q5_test exists and is forbidden in Batch 5-D")
    if args.provider != "deepseek" or args.model != "deepseek-v4-flash":
        errors.append("Batch 5-D primary identity must be deepseek/deepseek-v4-flash")
    if args.temperature != 0.0 or args.thinking_mode != "disabled":
        errors.append("controlled Q5 primary requires temperature=0 and thinking=disabled")
    if args.max_output_tokens != 512 or args.timeout_seconds != 30.0:
        errors.append("controlled Q5 primary requires max_output_tokens=512 and timeout=30")
    real_run_dir = args.real_output_root / args.real_run_id
    real_run_directory_absent = not real_run_dir.exists()
    if not real_run_directory_absent:
        errors.append(f"planned real run directory already exists: {real_run_dir}")

    pre_run = check_q5_pre_run(args.dataset_root, dataset_partition="dev")
    if not pre_run.valid:
        errors.extend(f"dataset pre-run: {message}" for message in pre_run.errors)
    tasks = load_q5_tasks(args.dataset_root / "tasks.jsonl")
    if len(tasks) != Q5_REAL_CASE_COUNT:
        errors.append(
            f"q5_dev must contain {Q5_REAL_CASE_COUNT} tasks, got {len(tasks)}"
        )

    verified_mock = None
    try:
        verified_mock = verify_q5_graded_run(
            args.mock_run,
            args.dataset_root / "gold.jsonl",
        )
    except (OSError, TypeError, ValueError) as exc:
        errors.append(f"mock anchor verification failed: {type(exc).__name__}")
    if verified_mock is not None:
        if verified_mock.git_commit_sha != commit:
            errors.append(
                "mock topology forecast is not anchored to the execution commit: "
                f"mock={verified_mock.git_commit_sha} execution={commit}"
            )
        if (
            verified_mock.protocol_version != "v2"
            or verified_mock.mode != "mock"
            or not verified_mock.mock_used
            or verified_mock.real_run
        ):
            errors.append("mock anchor must be a verified protocol-v2 mock run")

    topology: dict[str, Any] | None = None
    try:
        topology = _validate_mock_topology(
            q5_read_jsonl(args.mock_run / "results.jsonl"),
            q5_read_json(args.mock_run / "manifest.json"),
            case_ids=[task.case_id for task in tasks],
            systems=Q5_REAL_SYSTEMS,
            k=args.k,
        )
    except (OSError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    expected_trials = len(tasks) * len(Q5_REAL_SYSTEMS) * args.k
    by_system = Counter(
        (topology or {}).get("expected_calls_by_system", {})
    )
    model_called_trials = Counter(
        (topology or {}).get("expected_model_called_trials_by_system", {})
    )
    expected_calls = int((topology or {}).get("expected_total_calls", 0))
    hard_call_limit = int((topology or {}).get("hard_call_limit", 0))

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
    command = _real_command(args)
    if "--gold" in command or "q5/test" in command or "q5\\test" in command:
        errors.append("planned runtime command crosses the task/gold or dev/test boundary")

    payload: dict[str, object] = {
        "schema_version": Q5_REAL_PREFLIGHT_SCHEMA,
        "valid": not errors,
        "request_policy": {
            "completion_requests_sent_during_preflight": 0,
            "http_model_requests_sent_during_preflight": 0,
            "provider_model_calls_during_preflight": calls_after - calls_before,
            "tls_handshake_only": True,
        },
        "freeze": {
            "git_commit_sha": commit,
            "worktree_clean": worktree_clean,
            "q5_test_absent": not (Path("data/q5") / "test").exists(),
            "real_run_directory_absent": real_run_directory_absent,
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
            "systems": list(Q5_REAL_SYSTEMS),
            "k": args.k,
            "expected_trial_count": expected_trials,
            "sha256": pre_run.sha256,
            "mock_topology_run": (
                verified_mock.run_id if verified_mock is not None else None
            ),
            "mock_topology_manifest_sha256": (
                verified_mock.raw_manifest_sha256
                if verified_mock is not None
                else None
            ),
            "mock_topology": topology,
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
            "cost_and_token_observability_only": True,
            "validity_blocking_cost_cap_usd": None,
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


def _validate_mock_topology(
    rows: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    *,
    case_ids: Sequence[str],
    systems: Sequence[str],
    k: int,
) -> dict[str, Any]:
    """Validate the complete mock trial matrix used to forecast the real run."""

    errors: list[str] = []
    expected_cases = tuple(sorted(str(case_id) for case_id in case_ids))
    expected_systems = tuple(str(system) for system in systems)
    expected_indexes = tuple(range(1, k + 1))
    expected_keys = {
        (case_id, system, run_index)
        for case_id in expected_cases
        for system in expected_systems
        for run_index in expected_indexes
    }
    expected_count = len(expected_keys)

    if len(expected_cases) != len(set(expected_cases)):
        errors.append("expected case IDs contain duplicates")
    if len(expected_systems) != len(set(expected_systems)):
        errors.append("expected systems contain duplicates")
    if k != Q5_REAL_K:
        errors.append(f"execution k must be {Q5_REAL_K}, got {k}")

    manifest_systems = manifest.get("systems")
    if manifest_systems != list(expected_systems):
        errors.append("manifest systems do not match execution systems")
    manifest_cases = manifest.get("case_ids")
    if manifest_cases != list(expected_cases):
        errors.append("manifest case IDs do not match execution case IDs")
    if manifest.get("k") != k:
        errors.append(f"manifest k does not match execution k={k}")
    for field in ("trial_count", "expected_trial_count"):
        if manifest.get(field) != expected_count:
            errors.append(
                f"manifest {field} must be {expected_count}, got {manifest.get(field)}"
            )
    artifact_counts = manifest.get("artifact_row_counts")
    if (
        not isinstance(artifact_counts, Mapping)
        or artifact_counts.get("results.jsonl") != expected_count
    ):
        errors.append(
            f"manifest results row count must be {expected_count}"
        )
    if len(rows) != expected_count:
        errors.append(f"mock results must contain {expected_count} rows, got {len(rows)}")

    trial_keys: list[tuple[str, str, int]] = []
    rows_per_index: Counter[int] = Counter()
    cases_by_index_system: dict[tuple[int, str], set[str]] = {}
    expected_calls_by_system: Counter[str] = Counter(
        {system: 0 for system in expected_systems}
    )
    called_trials_by_system: Counter[str] = Counter(
        {system: 0 for system in expected_systems}
    )
    invalid_row_count = 0
    for row in rows:
        case_id = row.get("case_id")
        system = row.get("system")
        run_index = row.get("run_index")
        llm_calls = row.get("llm_calls")
        if (
            not isinstance(case_id, str)
            or not isinstance(system, str)
            or type(run_index) is not int
            or type(llm_calls) is not int
            or llm_calls < 0
        ):
            invalid_row_count += 1
            continue
        key = (case_id, system, run_index)
        trial_keys.append(key)
        rows_per_index[run_index] += 1
        cases_by_index_system.setdefault((run_index, system), set()).add(case_id)
        if system in expected_systems:
            expected_calls_by_system[system] += llm_calls
            if llm_calls > 0:
                called_trials_by_system[system] += 1
    if invalid_row_count:
        errors.append(f"mock results contain {invalid_row_count} malformed trial rows")

    duplicate_keys = [
        key for key, count in Counter(trial_keys).items() if count != 1
    ]
    if duplicate_keys:
        errors.append(f"mock results contain {len(duplicate_keys)} duplicate trial keys")
    actual_keys = set(trial_keys)
    missing_keys = expected_keys - actual_keys
    extra_keys = actual_keys - expected_keys
    if missing_keys:
        errors.append(f"mock results are missing {len(missing_keys)} trial keys")
    if extra_keys:
        errors.append(f"mock results contain {len(extra_keys)} unexpected trial keys")

    actual_indexes = tuple(sorted(rows_per_index))
    if actual_indexes != expected_indexes:
        errors.append(
            f"mock run indexes must be {list(expected_indexes)}, got {list(actual_indexes)}"
        )
    expected_rows_per_index = len(expected_cases) * len(expected_systems)
    for run_index in expected_indexes:
        if rows_per_index[run_index] != expected_rows_per_index:
            errors.append(
                f"run_index={run_index} must contain {expected_rows_per_index} rows, "
                f"got {rows_per_index[run_index]}"
            )
        for system in expected_systems:
            actual_cases = cases_by_index_system.get((run_index, system), set())
            if actual_cases != set(expected_cases):
                errors.append(
                    f"run_index={run_index} system={system} case topology mismatch"
                )

    if errors:
        raise ValueError("mock topology invalid: " + "; ".join(errors))

    expected_total_calls = sum(expected_calls_by_system.values())
    hard_call_limit = (
        sum(called_trials_by_system.values()) * MAX_Q5_POLICY_STEPS
    )
    return {
        "case_count": len(expected_cases),
        "systems": list(expected_systems),
        "k": k,
        "trial_count": expected_count,
        "run_indexes": list(expected_indexes),
        "rows_per_run_index": {
            str(run_index): rows_per_index[run_index]
            for run_index in expected_indexes
        },
        "unique_trial_key_count": len(actual_keys),
        "expected_calls_by_system": dict(sorted(expected_calls_by_system.items())),
        "expected_model_called_trials_by_system": dict(
            sorted(called_trials_by_system.items())
        ),
        "expected_total_calls": expected_total_calls,
        "hard_call_limit": hard_call_limit,
    }


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
        "py -m uv run --frozen python",
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
