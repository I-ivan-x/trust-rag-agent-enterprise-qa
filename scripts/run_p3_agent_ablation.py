# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.core.enums import EvalSplit
from app.eval.agent_attribution import compute_agent_attribution
from app.eval.dataset import (
    chunk_path_for_split,
    load_eval_cases,
    read_jsonl,
    write_jsonl,
)
from app.eval.metrics import summarize_results
from app.eval.passk import compute_passk
from app.eval.runner import _is_failure, _run_case_real
from app.llm.usage import get_usage_tracker
from app.schemas.eval import EvalCase, EvalResult
from scripts.rebuild_indexes import rebuild_indexes

SYSTEMS = [
    "final_gated_calibrated",
    "final_agentic_v2_rule",
    "final_agentic_v2_llm",
]
DEFAULT_RUN_ID = "p3-09-agent-ablation"
DEFAULT_EXTERNAL_SOURCE = Path(
    "data/eval_runs/q2-p1-06-reconciled-legacy-default/results.jsonl"
)
LEGAL_TRIGGER_CASES = [
    {"split": "obfuscated", "case_id": "obfuscated-015", "action": "rewrite_query"},
    {"split": "agent_residual", "case_id": "AR-002", "action": "rewrite_query"},
]
DIAGNOSTIC_ANCHOR = {
    "precheck_doc": "docs/P3_09_DIAGNOSTIC_PRECHECK.md",
    "case_count": 33,
    "failure_distribution": {
        "NO_RECOVERY": 29,
        "PERMISSION_BLOCKED": 2,
        "WEAK_RECALL": 2,
    },
    "action_a_legal_trigger_count": 2,
    "action_b_legal_trigger_count": 0,
    "action_b_gold_doc_recoverable_count": 0,
    "action_d_legal_trigger_count": 0,
}


@dataclass(frozen=True)
class SelectedCase:
    split: EvalSplit
    case: EvalCase
    group: str

    @property
    def key(self) -> str:
        return f"{self.split.value}:{self.case.case_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Q2 Phase 3 P3-09/P3-10 real agent ablation."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument(
        "--external-source-results",
        type=Path,
        default=DEFAULT_EXTERNAL_SOURCE,
        help="Prior calibrated external run used to select false-refusal controls.",
    )
    parser.add_argument("--no-reports", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_p3_agent_ablation(
        run_id=args.run_id,
        k=args.k,
        output_root=args.output_root,
        max_output_tokens=args.max_output_tokens,
        sleep_seconds=args.sleep_seconds,
        external_source_results=args.external_source_results,
        write_reports=not args.no_reports,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def run_p3_agent_ablation(
    *,
    run_id: str = DEFAULT_RUN_ID,
    k: int = 3,
    output_root: Path | None = None,
    max_output_tokens: int | None = 512,
    sleep_seconds: float = 0.2,
    external_source_results: Path = DEFAULT_EXTERNAL_SOURCE,
    write_reports: bool = True,
) -> dict[str, Any]:
    if k <= 0:
        raise ValueError("k must be positive")
    _require_real_llm_ready()

    run_dir = (output_root or get_settings().eval_runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    selected_cases, selection = _build_testbed(external_source_results)
    public_cases = [
        selected
        for selected in selected_cases
        if selected.split in {EvalSplit.obfuscated, EvalSplit.external}
    ]
    residual_cases = [
        selected
        for selected in selected_cases
        if selected.split is EvalSplit.agent_residual
    ]

    get_usage_tracker().reset()
    result_models: list[EvalResult] = []
    result_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    answer_rows: list[dict[str, Any]] = []
    llm_call_rows: list[dict[str, Any]] = []
    group_by_result: list[tuple[str, EvalResult]] = []
    index_summaries: list[dict[str, Any]] = []
    vector_unavailable_any = False
    reranker_unavailable_any = False

    index_summaries.append(_rebuild_for_split(EvalSplit.obfuscated))
    _run_selected_cases(
        public_cases,
        run_id=run_id,
        k=k,
        max_output_tokens=max_output_tokens,
        sleep_seconds=sleep_seconds,
        result_models=result_models,
        result_rows=result_rows,
        trace_rows=trace_rows,
        failure_rows=failure_rows,
        audit_rows=audit_rows,
        answer_rows=answer_rows,
        llm_call_rows=llm_call_rows,
        group_by_result=group_by_result,
    )

    if residual_cases:
        index_summaries.append(_rebuild_for_split(EvalSplit.agent_residual))
        _run_selected_cases(
            residual_cases,
            run_id=run_id,
            k=k,
            max_output_tokens=max_output_tokens,
            sleep_seconds=sleep_seconds,
            result_models=result_models,
            result_rows=result_rows,
            trace_rows=trace_rows,
            failure_rows=failure_rows,
            audit_rows=audit_rows,
            answer_rows=answer_rows,
            llm_call_rows=llm_call_rows,
            group_by_result=group_by_result,
        )

    for row in result_rows:
        if row.get("vector_unavailable"):
            vector_unavailable_any = True
        if row.get("reranker_unavailable"):
            reranker_unavailable_any = True

    usage = get_usage_tracker().totals
    summary = _build_p3_summary(
        run_id=run_id,
        run_dir=run_dir,
        k=k,
        selected_cases=selected_cases,
        selection=selection,
        result_models=result_models,
        result_rows=result_rows,
        trace_rows=trace_rows,
        audit_rows=audit_rows,
        group_by_result=group_by_result,
        llm_call_rows=llm_call_rows,
        index_summaries=index_summaries,
        vector_unavailable_any=vector_unavailable_any,
        reranker_unavailable_any=reranker_unavailable_any,
        usage=usage,
    )

    write_jsonl(run_dir / "results.jsonl", result_rows)
    write_jsonl(run_dir / "traces.jsonl", trace_rows)
    write_jsonl(run_dir / "failures.jsonl", failure_rows)
    write_jsonl(run_dir / "citation_audit_sample.jsonl", audit_rows[:25])
    write_jsonl(run_dir / "answers.jsonl", answer_rows)
    write_jsonl(run_dir / "llm_call_deltas.jsonl", llm_call_rows)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if write_reports:
        _write_evaluation_report(Path("docs/EVALUATION_REPORT.md"), summary)
        _write_failure_analysis(Path("docs/FAILURE_ANALYSIS.md"), summary, failure_rows)

    if vector_unavailable_any:
        raise RuntimeError(
            "P3 real run produced vector_unavailable=true; summary was written but "
            "the run is not acceptable for P3-09."
        )
    return summary


def _run_selected_cases(
    selected_cases: list[SelectedCase],
    *,
    run_id: str,
    k: int,
    max_output_tokens: int | None,
    sleep_seconds: float,
    result_models: list[EvalResult],
    result_rows: list[dict[str, Any]],
    trace_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]],
    answer_rows: list[dict[str, Any]],
    llm_call_rows: list[dict[str, Any]],
    group_by_result: list[tuple[str, EvalResult]],
) -> None:
    tracker = get_usage_tracker()
    for run_index in range(1, k + 1):
        for system_name in SYSTEMS:
            for selected in selected_cases:
                before = _usage_snapshot()
                row = _run_case_real(
                    selected.case,
                    system_name,
                    run_id=run_id,
                    max_output_tokens=max_output_tokens,
                    evidence_gate_config=None,
                    trust_gate_policy=None,
                )
                after = _usage_snapshot()
                delta = _usage_delta(before, after)
                result = row["result"]
                trace_id = (
                    f"trace-r{run_index}-{selected.split.value}-"
                    f"{selected.case.case_id}-{system_name}"
                )
                result.trace_id = trace_id
                result_models.append(result)
                group_by_result.append((selected.group, result))

                result_row = result.model_dump(mode="json")
                result_row.update(
                    {
                        "run_index": run_index,
                        "testbed_group": selected.group,
                        "testbed_case_key": selected.key,
                        "vector_unavailable": row.get("vector_unavailable", False),
                        "reranker_unavailable": row.get("reranker_unavailable", False),
                    }
                )
                result_rows.append(result_row)

                trace = dict(row["trace"])
                trace.update(
                    {
                        "trace_id": trace_id,
                        "run_index": run_index,
                        "testbed_group": selected.group,
                        "testbed_case_key": selected.key,
                    }
                )
                trace_rows.append(trace)

                audit = row.get("audit")
                if audit is not None:
                    audit_rows.append(
                        {
                            **audit,
                            "run_index": run_index,
                            "testbed_group": selected.group,
                            "testbed_case_key": selected.key,
                        }
                    )
                answer = row.get("answer")
                if answer is not None:
                    answer_rows.append(
                        {
                            **answer,
                            "run_index": run_index,
                            "testbed_group": selected.group,
                            "testbed_case_key": selected.key,
                        }
                    )
                if _is_failure(result, selected.case):
                    failure_rows.append(
                        {
                            **row["failure"],
                            "run_index": run_index,
                            "split": selected.split.value,
                            "testbed_group": selected.group,
                            "testbed_case_key": selected.key,
                        }
                    )

                llm_call_rows.append(
                    {
                        "run_index": run_index,
                        "split": selected.split.value,
                        "case_id": selected.case.case_id,
                        "system_name": system_name,
                        "testbed_group": selected.group,
                        **delta,
                        "tracker_total_calls_after": tracker.totals.total_calls,
                    }
                )
                if sleep_seconds > 0 and delta["total_calls"] > 0:
                    time.sleep(sleep_seconds)


def _build_testbed(source_results: Path) -> tuple[list[SelectedCase], dict[str, Any]]:
    obfuscated = load_eval_cases(EvalSplit.obfuscated)
    external = {case.case_id: case for case in load_eval_cases(EvalSplit.external)}
    agent_residual = {
        case.case_id: case for case in load_eval_cases(EvalSplit.agent_residual)
    }
    external_ids = _external_false_refusal_ids(source_results)[:6]

    selected: list[SelectedCase] = []
    seen: set[str] = set()

    for case in obfuscated:
        _append_unique(
            selected,
            seen,
            SelectedCase(EvalSplit.obfuscated, case, "obfuscated"),
        )
    for case_id in external_ids:
        if case_id not in external:
            raise ValueError(f"External false-refusal case not found: {case_id}")
        _append_unique(
            selected,
            seen,
            SelectedCase(EvalSplit.external, external[case_id], "external_false_refusal"),
        )
    if "AR-002" not in agent_residual:
        raise ValueError("agent_residual legal-trigger case AR-002 not found")
    _append_unique(
        selected,
        seen,
        SelectedCase(EvalSplit.agent_residual, agent_residual["AR-002"], "legal_trigger"),
    )

    selection = {
        "policy": (
            "obfuscated all 15 + first six calibrated external false-refusals "
            "by case_id + legal-trigger AR-002; hard-negative excluded."
        ),
        "obfuscated_case_count": len(obfuscated),
        "external_false_refusal_source": source_results.as_posix(),
        "external_false_refusal_case_ids": external_ids,
        "legal_trigger_cases": LEGAL_TRIGGER_CASES,
        "hard_negative_included": False,
        "unique_case_count": len(selected),
        "case_keys": [case.key for case in selected],
    }
    return selected, selection


def _external_false_refusal_ids(path: Path) -> list[str]:
    rows = read_jsonl(path)
    case_ids = {
        str(row["case_id"])
        for row in rows
        if row.get("eval_split") == EvalSplit.external.value
        and (row.get("metrics") or {}).get("false_refusal_rate") is True
    }
    return sorted(case_ids)


def _append_unique(
    selected: list[SelectedCase],
    seen: set[str],
    item: SelectedCase,
) -> None:
    if item.key in seen:
        return
    selected.append(item)
    seen.add(item.key)


def _build_p3_summary(
    *,
    run_id: str,
    run_dir: Path,
    k: int,
    selected_cases: list[SelectedCase],
    selection: dict[str, Any],
    result_models: list[EvalResult],
    result_rows: list[dict[str, Any]],
    trace_rows: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]],
    group_by_result: list[tuple[str, EvalResult]],
    llm_call_rows: list[dict[str, Any]],
    index_summaries: list[dict[str, Any]],
    vector_unavailable_any: bool,
    reranker_unavailable_any: bool,
    usage,
) -> dict[str, Any]:
    settings = get_settings()
    group_metrics: dict[str, dict[str, Any]] = {}
    for group in sorted({group for group, _ in group_by_result}):
        group_metrics[group] = summarize_results(
            [result for row_group, result in group_by_result if row_group == group]
        )

    llm_calls_by_system: dict[str, dict[str, int]] = {}
    for system in SYSTEMS:
        system_rows = [row for row in llm_call_rows if row["system_name"] == system]
        llm_calls_by_system[system] = {
            "answer_calls": sum(int(row["answer_calls"]) for row in system_rows),
            "controller_calls": sum(int(row["controller_calls"]) for row in system_rows),
            "rewrite_calls": sum(int(row["rewrite_calls"]) for row in system_rows),
            "total_calls": sum(int(row["total_calls"]) for row in system_rows),
        }

    agent_attribution = compute_agent_attribution(trace_rows, result_models)
    agent_attribution_by_system = {
        system: attribution
        for system in ("final_agentic_v2_rule", "final_agentic_v2_llm")
        if (
            attribution := compute_agent_attribution(
                [row for row in trace_rows if row.get("system_name") == system],
                [result for result in result_models if result.system_name == system],
            )
        )
        is not None
    }

    summary: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "systems": SYSTEMS,
        "mode": "real_run",
        "split": "p3_agent_ablation_mixed",
        "eval_split": "mixed",
        "num_cases": len(selected_cases),
        "k": k,
        "attempt_count": len(result_rows),
        "headline_eligible": False,
        "headline_scope": "agent_phase3_diagnostic",
        "headline_policy": (
            "P3 agent ablation mixes obfuscated, external false-refusal controls, "
            "and agent_residual diagnostic cases; it must not enter external headline metrics."
        ),
        "agent_residual_run": True,
        "pilot_eligible": False,
        "full_split_run": False,
        "mock_used": False,
        "toy_retrieval": False,
        "expected_rewrite_used": False,
        "formal_retrieval_baseline": False,
        "uses_real_llm": settings.llm_provider.lower() != "mock",
        "uses_real_embedding": all(
            summary.get("embedding_provider") != "mock" for summary in index_summaries
        ),
        "uses_real_reranker": not reranker_unavailable_any,
        "llm_provider": settings.llm_provider,
        "llm_model_name": settings.llm_model_name,
        "rewrite_llm_provider": settings.rewrite_llm_provider,
        "rewrite_llm_model_name": settings.rewrite_llm_model_name,
        "reranker_unavailable": reranker_unavailable_any,
        "vector_unavailable": vector_unavailable_any,
        "llm_call_count": usage.total_calls,
        "answer_llm_call_count": usage.answer_calls,
        "controller_llm_call_count": usage.other_calls,
        "rewrite_llm_call_count": usage.rewrite_calls,
        "llm_usage_prompt_tokens": usage.prompt_tokens,
        "llm_usage_completion_tokens": usage.completion_tokens,
        "llm_usage_total_tokens": usage.total_tokens,
        "llm_usage_reported": usage.usage_reported,
        "real_llm_invoked": usage.total_calls > 0,
        "summary_metrics": summarize_results(result_models),
        "summary_metrics_by_group": group_metrics,
        "passk": compute_passk(result_rows, trace_rows, k=k),
        "agent_attribution": agent_attribution,
        "agent_attribution_by_system": agent_attribution_by_system,
        "llm_calls_by_system": llm_calls_by_system,
        "testbed": selection,
        "diagnostic_anchor": DIAGNOSTIC_ANCHOR,
        "index_summaries": index_summaries,
        "audit_row_count": len(audit_rows),
        "run_dir": run_dir.as_posix(),
        "expected_rewrite_policy": (
            "expected_rewrite is informational only and is never used for retrieval or scoring."
        ),
        "p3_interpretation": {
            "phenomenon": (
                "Agent action b/d effective trigger surface is zero and action-a "
                "recoveries are confined to the legal-trigger diagnostic corner."
            ),
            "root_cause": (
                "Residual false-refusals are policy-adjudication failures, not "
                "gold-doc-recoverable metadata-filtering failures."
            ),
            "next_step": (
                "Keep the mechanism; treat the apparent agent delta as qualitative "
                "small-n diagnostic evidence, not a headline gain."
            ),
        },
    }
    return summary


def _rebuild_for_split(split: EvalSplit) -> dict[str, Any]:
    summary = rebuild_indexes(
        chunk_path_for_split(split),
        include_agent_residual=split is EvalSplit.agent_residual,
    )
    if not summary.get("vector_index_built"):
        raise RuntimeError(
            f"Vector index did not build for {split.value}; Qdrant must be available."
        )
    # The real pipeline caches retriever objects; clear after switching index state.
    from app.eval import real_pipeline

    real_pipeline._get_eval_hybrid_retriever.cache_clear()
    return summary


def _require_real_llm_ready() -> None:
    settings = get_settings()
    if settings.llm_provider.lower() == "mock":
        raise RuntimeError("P3 real run requires LLM_PROVIDER to be non-mock.")
    if settings.llm_provider.lower() == "deepseek" and not settings.deepseek_api_key:
        raise RuntimeError("P3 real run requires the DeepSeek API key to be configured.")
    if settings.llm_provider.lower() != "deepseek" and not settings.openai_api_key:
        raise RuntimeError("P3 real run requires an API key to be configured.")


def _usage_snapshot() -> dict[str, int]:
    totals = get_usage_tracker().totals
    return {
        "answer_calls": totals.answer_calls,
        "controller_calls": totals.other_calls,
        "rewrite_calls": totals.rewrite_calls,
        "total_calls": totals.total_calls,
    }


def _usage_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


def _write_evaluation_report(path: Path, summary: dict[str, Any]) -> None:
    metrics = summary.get("summary_metrics") or {}
    passk = (summary.get("passk") or {}).get("by_system") or {}
    calls = summary.get("llm_calls_by_system") or {}
    attribution = summary.get("agent_attribution") or {}
    attribution_by_system = summary.get("agent_attribution_by_system") or {}
    per_action = attribution.get("per_action") or {}
    controller = attribution.get("controller") or {}
    testbed = summary.get("testbed") or {}
    anchor = summary.get("diagnostic_anchor") or {}

    lines = [
        "# Evaluation Report",
        "",
        "## Q2 Phase 3 P3-09/P3-10 Agent Ablation",
        "",
        f"- run_id: `{summary.get('run_id')}`",
        f"- run_dir: `{summary.get('run_dir')}`",
        f"- systems: `{', '.join(summary.get('systems') or [])}`",
        f"- cases: `{summary.get('num_cases')}` unique x `k={summary.get('k')}`",
        f"- mode: `{summary.get('mode')}`",
        f"- headline_eligible: `{summary.get('headline_eligible')}`",
        f"- headline_scope: `{summary.get('headline_scope')}`",
        f"- mock_used: `{summary.get('mock_used')}`",
        f"- toy_retrieval: `{summary.get('toy_retrieval')}`",
        f"- expected_rewrite_used: `{summary.get('expected_rewrite_used')}`",
        f"- vector_unavailable: `{summary.get('vector_unavailable')}`",
        f"- llm_call_count: `{summary.get('llm_call_count')}` "
        f"(answer `{summary.get('answer_llm_call_count')}`, "
        f"controller `{summary.get('controller_llm_call_count')}`, "
        f"rewrite `{summary.get('rewrite_llm_call_count')}`)",
        f"- llm_usage_total_tokens: `{summary.get('llm_usage_total_tokens')}`",
        "",
        "> Diagnostic-only P3 agent ablation. agent_residual/AR cases and this mixed "
        "testbed never enter external headline metrics.",
        "",
        "### Metric Boundary Carry-Forward",
        "",
        "Retrieval-tier metrics measure whether gold evidence is retrieved, not whether "
        "the final answer is correct.",
        "",
        "Week 6 boundary retained: final_agentic did not outperform final_gated; P3 "
        "agent deltas are diagnostic small-n observations, not headline claims.",
        "",
        "### Testbed",
        "",
        "| slice | count / ids |",
        "| --- | --- |",
        f"| obfuscated | {testbed.get('obfuscated_case_count')} cases |",
        (
            "| external false-refusal controls | "
            f"{', '.join(testbed.get('external_false_refusal_case_ids') or [])} |"
        ),
        "| legal-trigger | obfuscated-015, AR-002 |",
        "| hard-negative | excluded |",
        "",
        "### Grounded And Reliability",
        "",
        "| system | grounded | pass^1 attempt mean | pass^3 | action sequence consistency |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for system in summary.get("systems") or []:
        system_metrics = metrics.get(system) or {}
        system_passk = passk.get(system) or {}
        lines.append(
            "| {system} | {grounded} | {pass1} | {pass3} | {consistency} |".format(
                system=system,
                grounded=_fmt(system_metrics.get("grounded_correctness")),
                pass1=_fmt(system_passk.get("pass_1_attempt_mean")),
                pass3=_fmt(system_passk.get("pass_3")),
                consistency=_fmt(system_passk.get("action_sequence_consistency")),
            )
        )

    lines.extend(
        [
            "",
            "### LLM Calls",
            "",
            "| system | answer | controller | rewrite | total |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for system in summary.get("systems") or []:
        row = calls.get(system) or {}
        lines.append(
            "| {system} | {answer} | {controller} | {rewrite} | {total} |".format(
                system=system,
                answer=row.get("answer_calls", 0),
                controller=row.get("controller_calls", 0),
                rewrite=row.get("rewrite_calls", 0),
                total=row.get("total_calls", 0),
            )
        )

    lines.extend(
        [
            "",
            "### Agent Attribution",
            "",
            "| action | trigger | accept | success | false_recovery_count | ineffective |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for action in (
        "rewrite_query",
        "filtered_retrieval",
        "present_conflict_set",
        "refuse_with_explanation",
    ):
        row = per_action.get(action) or {}
        lines.append(
            "| {action} | {trigger} | {accept} | {success} | {false} | {ineffective} |".format(
                action=action,
                trigger=row.get("trigger_count", 0),
                accept=row.get("accept_count", 0),
                success=row.get("success_count", 0),
                false=row.get("false_recovery_count", 0),
                ineffective=row.get("ineffective", 0),
            )
        )

    lines.extend(
        [
            "",
            "LLM controller:",
            "",
            f"- llm_propose_count: `{controller.get('llm_propose_count', 0)}`",
            f"- llm_accept_count: `{controller.get('llm_accept_count', 0)}`",
            f"- llm_fallback_count: `{controller.get('llm_fallback_count', 0)}`",
            f"- llm_fallback_rate: `{controller.get('llm_fallback_rate', 0.0)}`",
            "",
            "Per-system action attribution:",
            "",
            "| system | action | trigger | accept | success | false_recovery_count | ineffective |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for system in ("final_agentic_v2_rule", "final_agentic_v2_llm"):
        system_attr = attribution_by_system.get(system) or {}
        system_actions = system_attr.get("per_action") or {}
        for action in (
            "rewrite_query",
            "filtered_retrieval",
            "present_conflict_set",
            "refuse_with_explanation",
        ):
            row = system_actions.get(action) or {}
            lines.append(
                "| {system} | {action} | {trigger} | {accept} | {success} | "
                "{false} | {ineffective} |".format(
                    system=system,
                    action=action,
                    trigger=row.get("trigger_count", 0),
                    accept=row.get("accept_count", 0),
                    success=row.get("success_count", 0),
                    false=row.get("false_recovery_count", 0),
                    ineffective=row.get("ineffective", 0),
                )
            )

    lines.extend(
        [
            "",
            "### Diagnostic Anchor",
            "",
            (
                f"P3-09 zero-token precheck: {anchor.get('case_count')} cases; "
                f"failure distribution `{anchor.get('failure_distribution')}`; "
                f"a legal trigger={anchor.get('action_a_legal_trigger_count')}, "
                f"b legal trigger={anchor.get('action_b_legal_trigger_count')}, "
                f"b gold-doc-recoverable={anchor.get('action_b_gold_doc_recoverable_count')}, "
                f"d legal trigger={anchor.get('action_d_legal_trigger_count')}."
            ),
            "",
            "### P3-11 Interpretation",
            "",
            "Phenomenon: action b/d have no legal trigger and action-a recovery is "
            "confined to the legal-trigger diagnostic corner. The small observed delta "
            "is not a headline gain.",
            "",
            "Root cause: the remaining false-refusals are policy-adjudication style "
            "failures (F1/F2), not retrieval recoveries. Action b has a broad diagnostic "
            "surface, but gold-doc-recoverable remains 0, and filtered retrieval does not "
            "bypass ACL/state gates.",
            "",
            "Next step: treat the mechanism as usable and guarded, while recording that "
            "the current frozen testbed has no broad measurable agent gain. The "
            "dual-controller ablation has degraded to a vs e on n=2 legal-trigger "
            "cases, so it is qualitative and statistically powerless.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_failure_analysis(
    path: Path,
    summary: dict[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    reason_counts = Counter(str(row.get("reason", "unknown")) for row in failures)
    by_system = Counter(str(row.get("system_name", "unknown")) for row in failures)
    by_group = Counter(str(row.get("testbed_group", "unknown")) for row in failures)
    trajectory = (
        (summary.get("agent_attribution") or {}).get("trajectory_failures") or {}
    )
    lines = [
        "# Failure Analysis",
        "",
        "## Q2 Phase 3 P3-09/P3-10",
        "",
        f"- run_id: `{summary.get('run_id')}`",
        f"- failure rows: `{len(failures)}`",
        f"- headline_eligible: `{summary.get('headline_eligible')}`",
        "",
        "### Failure Distribution",
        "",
        "```json",
        json.dumps(
            {
                "by_reason": dict(sorted(reason_counts.items())),
                "by_system": dict(sorted(by_system.items())),
                "by_testbed_group": dict(sorted(by_group.items())),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "### Trajectory Failure Taxonomy",
        "",
        "| code | meaning | count |",
        "| --- | --- | ---: |",
        (
            "| TF1 | wrong action; replay candidate only | "
            f"{trajectory.get('tf1_candidate_count', 0)} |"
        ),
        (
            "| TF2 | ineffective action; evidence still insufficient | "
            f"{trajectory.get('tf2_ineffective_action_case_count', 0)} |"
        ),
        (
            "| TF3 | validator rejected an action | "
            f"{trajectory.get('tf3_validator_reject_step_count', 0)} |"
        ),
        f"| TF4 | budget exhausted | {trajectory.get('tf4_budget_exhausted_case_count', 0)} |",
        "",
        "### P3 Root Cause",
        "",
        "The residual failures are dominated by the already-known calibrated-gate boundary: "
        "false-refusal cases are policy adjudication failures rather than recoverable "
        "metadata-filtered retrieval failures. The P3 action space remains guarded: "
        "retrieval actions rerun ACL/state/evidence gates, and invalid LLM controller "
        "proposals fall back to the rule controller.",
        "",
        "Week 6 boundary retained: hard_negative_error_rate=1.0 indicates a serious "
        "failure mode.",
        "",
        "### Failure Samples",
        "",
    ]
    for failure in failures[:25]:
        lines.extend(
            [
                (
                    "#### {split}:{case_id} / {system} / run {run_index}".format(
                        split=failure.get("split", "n/a"),
                        case_id=failure.get("case_id", "n/a"),
                        system=failure.get("system_name", "n/a"),
                        run_index=failure.get("run_index", "n/a"),
                    )
                ),
                "",
                f"- group: `{failure.get('testbed_group', 'n/a')}`",
                f"- reason: `{failure.get('reason', 'n/a')}`",
                f"- query: {failure.get('query', 'n/a')}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    main()
