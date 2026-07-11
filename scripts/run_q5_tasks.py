# ruff: noqa: E402
"""Execute the gold-isolated Q5 harness."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.eval.q5_dataset import load_q5_runtime_dataset
from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_runner import (
    Q5RunSettings,
    load_q5_runtime_cases,
    run_q5_tasks,
)
from app.govern.q5_loop import Q5AgentSystem
from app.llm.llm_client import get_llm_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Q5 tasks without loading or accepting gold."
    )
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--runtime-cases", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260711)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--mode", choices=("mock", "dev", "real"), default="mock")
    parser.add_argument(
        "--model-role", choices=("primary", "confirmatory"), default="primary"
    )
    parser.add_argument("--provider", default="mock")
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument(
        "--thinking-mode",
        choices=("enabled", "disabled"),
        help="DeepSeek-only; controlled Q5 runs pass disabled explicitly.",
    )
    parser.add_argument(
        "--systems",
        nargs="+",
        choices=tuple(system.value for system in Q5AgentSystem),
        default=[system.value for system in Q5AgentSystem],
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(argv)
    dataset = load_q5_runtime_dataset(args.tasks, args.environment)
    runtime_cases = load_q5_runtime_cases(args.runtime_cases)
    if args.mode == "mock":
        if args.provider not in {"mock", "deterministic_mock"}:
            raise ValueError("Q5 mock mode only accepts the deterministic mock provider")
        model = Q5DeterministicMockPolicyModel()
    else:
        model = get_llm_client(
            args.provider,
            model_name=args.model,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            timeout=args.timeout_seconds,
            thinking_mode=args.thinking_mode,
            purpose="q5_policy",
        )
    settings = Q5RunSettings(
        output_root=args.output_root,
        run_id=args.run_id,
        k=args.k,
        seed=args.seed,
        bootstrap_resamples=args.bootstrap_resamples,
        mode=args.mode,
        model_role=args.model_role,
    )
    artifacts = run_q5_tasks(
        dataset.tasks,
        dataset.environment,
        args.systems,
        runtime_cases=runtime_cases,
        settings=settings,
        model_factory=lambda task, system, run_index: model,
    )
    payload: dict[str, object] = {
        "run_dir": artifacts.run_dir.as_posix(),
        "manifest": artifacts.manifest_path.as_posix(),
        "trial_count": artifacts.trial_count,
    }
    print(json.dumps(payload, sort_keys=True))
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
