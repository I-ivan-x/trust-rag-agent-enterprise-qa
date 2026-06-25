# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.eval.dataset import load_eval_cases, write_jsonl
from app.eval.govern_runner import (
    build_governance_summary,
    governance_failure_rows,
    run_governance_case,
)
from app.eval.real_pipeline import _get_eval_hybrid_retriever, _get_eval_reranker
from app.govern.controller import GovernanceRuleController
from app.govern.llm_controller import GovernanceLLMController
from app.govern.sinks import LocalJsonlSink
from app.guards.evidence_gate import evidence_gate_config_from_settings
from app.llm.llm_client import get_llm_client
from app.llm.mock_llm import MockLLMClient
from scripts.ingest_corpus import run_ingest
from scripts.rebuild_indexes import rebuild_indexes

SYSTEMS = ["final_governed_rule", "final_governed_llm"]
DEFAULT_RUN_ID = "q3-p7-governance-ablation"
OPS_EVAL_PATH = Path("data/gold_eval/ops_runbook_action_v1_eval.jsonl")
OPS_CORPUS_DIR = Path("data/ops_runbook_corpus")
OPS_OVERLAY_PATH = OPS_CORPUS_DIR / "overlay" / "metadata_overlay.yaml"
OPS_GENERATED_DIR = Path("data/generated/ops_runbook")
OPS_CHUNKS_PATH = OPS_GENERATED_DIR / "chunks.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Q3 governance rule/LLM ablation.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--systems", default=",".join(SYSTEMS))
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--real-run", action="store_true")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument(
        "--split",
        default=None,
        help=(
            "Eval split to run (e.g. ops_dev for Q4-P4 dev calibration, ops_test for "
            "Q4-P5 held-out). Defaults to the original 14-case ops_runbook eval file. "
            "Do NOT pass ops_test during P3/P4."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_q3_governance_ablation(
        run_id=args.run_id,
        systems=_parse_systems(args.systems),
        k=args.k,
        real_run=args.real_run,
        output_root=args.output_root,
        sleep_seconds=args.sleep_seconds,
        max_output_tokens=args.max_output_tokens,
        split=args.split,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def run_q3_governance_ablation(
    *,
    run_id: str = DEFAULT_RUN_ID,
    systems: list[str] | None = None,
    k: int = 3,
    real_run: bool = False,
    output_root: Path | None = None,
    sleep_seconds: float = 0.2,
    max_output_tokens: int | None = 256,
    split: str | None = None,
) -> dict[str, Any]:
    if k <= 0:
        raise ValueError("k must be positive")
    selected_systems = systems or SYSTEMS
    unknown = sorted(set(selected_systems) - set(SYSTEMS))
    if unknown:
        raise ValueError(f"Unsupported governance systems: {', '.join(unknown)}")

    settings = get_settings()
    run_dir = (output_root or settings.eval_runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    index_summary = _prepare_ops_index()
    from app.eval import real_pipeline

    real_pipeline._get_eval_hybrid_retriever.cache_clear()
    real_pipeline._get_eval_reranker.cache_clear()
    retriever = _get_eval_hybrid_retriever()
    reranker, reranker_unavailable = _get_eval_reranker()
    vector_unavailable = not bool(index_summary.get("vector_index_built"))

    cases = load_eval_cases(split) if split else load_eval_cases(input_path=OPS_EVAL_PATH)
    result_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []

    for run_index in range(1, k + 1):
        for system_name in selected_systems:
            controller = _controller_for_system(
                system_name,
                real_run=real_run,
                max_output_tokens=max_output_tokens,
            )
            for case in cases:
                sink_root = run_dir / "action_store" / system_name / f"run-{run_index}"
                row = run_governance_case(
                    case,
                    controller,
                    retriever,
                    reranker,
                    settings,
                    system_name=system_name,
                    run_index=run_index,
                    evidence_gate_config=evidence_gate_config_from_settings(settings),
                    sink=LocalJsonlSink(sink_root),
                )
                result_rows.append(row["result"])
                trace_rows.append(row["trace"])
                if real_run and system_name == "final_governed_llm" and sleep_seconds > 0:
                    time.sleep(sleep_seconds)

    failure_rows = governance_failure_rows(result_rows)
    summary = build_governance_summary(
        run_id=run_id,
        run_dir=run_dir,
        systems=selected_systems,
        result_rows=result_rows,
        trace_rows=trace_rows,
        k=k,
        real_run=real_run,
        mock_used=not real_run,
        vector_unavailable=vector_unavailable,
        reranker_unavailable=reranker_unavailable,
        index_summaries=[index_summary],
    )

    write_jsonl(run_dir / "results.jsonl", result_rows)
    write_jsonl(run_dir / "traces.jsonl", trace_rows)
    write_jsonl(run_dir / "failures.jsonl", failure_rows)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if real_run and vector_unavailable:
        raise RuntimeError(
            "Q3 governance ablation produced vector_unavailable=true; summary was "
            "written but the run is not acceptable for Q3-P7."
        )
    return summary


def _prepare_ops_index() -> dict[str, Any]:
    run_ingest(
        input_dir=OPS_CORPUS_DIR,
        output_dir=OPS_GENERATED_DIR,
        eval_path=None,
        review_path=None,
        overlay_path=OPS_OVERLAY_PATH,
    )
    return rebuild_indexes(OPS_CHUNKS_PATH)


def _controller_for_system(
    system_name: str,
    *,
    real_run: bool,
    max_output_tokens: int | None,
):
    if system_name == "final_governed_rule":
        return GovernanceRuleController()
    client = (
        get_llm_client(
            get_settings().llm_provider,
            max_output_tokens=max_output_tokens,
            temperature=0,
            purpose="controller",
        )
        if real_run
        else MockLLMClient()
    )
    return GovernanceLLMController(client, fallback=GovernanceRuleController())


def _parse_systems(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


if __name__ == "__main__":
    main()
