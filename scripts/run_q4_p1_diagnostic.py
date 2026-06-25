# ruff: noqa: E402
"""Q4-P1 zero-token governance diagnostic (Q4_RELIABILITY_DESIGN §3.1).

Runs ``detect_conditions`` + the rule controller over the full ops set with
**no sink and no LLM** (reuses the P3-09 zero-token precheck pattern). It does
not change any logic; it only attributes:

* the ``flag_stale`` dead path -- for every ``STALE_PROCEDURE``-gold case it
  records whether ``detected_conditions`` contains ``STALE_PROCEDURE``
  (``no`` => detection miss / ``yes`` => routing error) and whether
  ``evidence_decision`` is ``insufficient`` (the insufficient->escalate
  short-circuit that swallows the flag), and
* over-escalation -- every case the rule controller escalates while gold is not
  ``escalate_to_human``, tagged with the escalate trigger.

The rule controller is deterministic, so one pass per case is sufficient
(unlike the LLM controller, which needs k>1). This run never instantiates an
LLM client and never writes to an action sink.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.eval.dataset import load_eval_cases, write_jsonl
from app.eval.govern_runner import _clearance_value, _requested_action
from app.govern.conditions import ActorContext, OpsCondition, detect_conditions
from app.govern.context import GovernanceControllerContext
from app.govern.controller import GovernanceRuleController
from app.guards.evidence_gate import evidence_gate_config_from_settings
from app.schemas.retrieval import RetrievalOptions
from app.workflow.orchestrator import run_trust_gated_pass
from scripts.ingest_corpus import run_ingest
from scripts.rebuild_indexes import rebuild_indexes

DEFAULT_RUN_ID = "q4-p1-diagnostic"
OPS_EVAL_PATH = Path("data/gold_eval/ops_runbook_action_v1_eval.jsonl")
OPS_CORPUS_DIR = Path("data/ops_runbook_corpus")
OPS_OVERLAY_PATH = OPS_CORPUS_DIR / "overlay" / "metadata_overlay.yaml"
OPS_GENERATED_DIR = Path("data/generated/ops_runbook")
OPS_CHUNKS_PATH = OPS_GENERATED_DIR / "chunks.jsonl"

PRECHECK_OPTIONS = RetrievalOptions(
    top_k_dense=20,
    top_k_sparse=20,
    top_n_rerank=8,
    return_trace=True,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q4-P1 zero-token governance diagnostic.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output-root", type=Path, default=Path("data/eval_runs"))
    parser.add_argument("--doc-output", type=Path, default=Path("docs/Q4_P1_DIAGNOSTIC.md"))
    parser.add_argument(
        "--write-doc",
        action="store_true",
        help="Also (re)generate the markdown report at --doc-output.",
    )
    parser.add_argument(
        "--allow-vector-unavailable",
        action="store_true",
        help=(
            "Record keyword-only fallback instead of failing when vector retrieval "
            "is unavailable (Qdrant down). The fallback is NOT representative of the "
            "headline diagnostic; bring Qdrant up for an authoritative run."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = args.output_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    index_summary = _prepare_ops_index()
    vector_unavailable = not bool(index_summary.get("vector_index_built"))
    if vector_unavailable and not args.allow_vector_unavailable:
        raise RuntimeError(
            "Vector index was not built (Qdrant down?). Diagnostic on keyword-only "
            "fallback is not representative; start Docker/Qdrant or pass "
            "--allow-vector-unavailable to record the fallback explicitly."
        )

    from app.eval import real_pipeline

    real_pipeline._get_eval_hybrid_retriever.cache_clear()
    real_pipeline._get_eval_reranker.cache_clear()
    retriever = real_pipeline._get_eval_hybrid_retriever()
    reranker, reranker_unavailable = real_pipeline._get_eval_reranker()

    cases = load_eval_cases(input_path=OPS_EVAL_PATH)
    gate_config = evidence_gate_config_from_settings(settings)
    controller = GovernanceRuleController()

    records: list[dict[str, Any]] = []
    for case in cases:
        pass_result = run_trust_gated_pass(
            query=case.query,
            retrieval_options=PRECHECK_OPTIONS,
            retriever=retriever,
            reranker=reranker,
            user_role=case.user_role,
            user_department=case.user_department,
            user_clearance=_clearance_value(case.user_clearance),
            evidence_gate_config=gate_config,
        )
        actor = ActorContext(
            role=case.user_role,
            clearance=_clearance_value(case.user_clearance),
            department=case.user_department,
            requested_action=_requested_action(case),
        )
        report = detect_conditions(pass_result, actor)
        context = GovernanceControllerContext.from_pass_result(pass_result)
        proposal = controller.select(report, context)  # no sink, no validator, no LLM
        records.append(_case_record(case, report, pass_result, proposal))

    summary = _build_summary(args.run_id, records, vector_unavailable, reranker_unavailable)
    payload = json.dumps(
        {"summary": summary, "cases": records}, ensure_ascii=False, indent=2, sort_keys=True
    )
    (run_dir / "diagnostic.json").write_text(payload + "\n", encoding="utf-8")
    write_jsonl(run_dir / "diagnostic_cases.jsonl", records)
    if args.write_doc:
        args.doc_output.write_text(_markdown(summary, records), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def _prepare_ops_index() -> dict[str, Any]:
    run_ingest(
        input_dir=OPS_CORPUS_DIR,
        output_dir=OPS_GENERATED_DIR,
        eval_path=None,
        review_path=None,
        overlay_path=OPS_OVERLAY_PATH,
    )
    return rebuild_indexes(OPS_CHUNKS_PATH)


def _case_record(case, report, pass_result, proposal) -> dict[str, Any]:
    detected = [c.value for c in report.conditions]
    gold_condition = str(case.gold_condition)
    gold_action = str(case.gold_action)
    proposed = proposal.action.value
    is_stale_gold = gold_condition == OpsCondition.stale_procedure.value
    stale_detected = OpsCondition.stale_procedure.value in detected
    evidence_insufficient = report.evidence_decision == "insufficient"

    dead_path_attr = None
    if is_stale_gold:
        # No STALE_PROCEDURE in detected_conditions => detection miss; else routing error.
        dead_path_attr = "routing_error" if stale_detected else "detection_miss"

    over_escalation = proposed == "escalate_to_human" and gold_action != "escalate_to_human"
    escalate_trigger = proposal.args.get("reason") if proposed == "escalate_to_human" else None

    return {
        "case_id": case.case_id,
        "gold_condition": gold_condition,
        "gold_action": gold_action,
        "authorized_gold": case.authorized,
        "user_role": case.user_role,
        "user_clearance": _clearance_value(case.user_clearance),
        "detected_conditions": detected,
        "authorized_actor": report.authorized_actor,
        "evidence_decision": report.evidence_decision,
        "permission_blocked_count": report.permission_blocked_count,
        "stale_doc_ids": report.stale_doc_ids,
        "proposed_action": proposed,
        "is_stale_gold": is_stale_gold,
        "stale_detected": stale_detected,
        "evidence_insufficient": evidence_insufficient,
        "dead_path_attribution": dead_path_attr,
        "over_escalation": over_escalation,
        "escalate_trigger": escalate_trigger,
        "blocked_chunk_ids": [
            r.chunk.chunk_id for r in pass_result.acl_decision.blocked_chunks
        ],
        "reranked_doc_ids": sorted({r.chunk.doc_id for r in pass_result.reranked_chunks}),
    }


def _build_summary(
    run_id: str,
    records: list[dict[str, Any]],
    vector_unavailable: bool,
    reranker_unavailable: bool,
) -> dict[str, Any]:
    stale_records = [r for r in records if r["is_stale_gold"]]
    over_records = [r for r in records if r["over_escalation"]]
    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "zero_token_governance_diagnostic",
        "controller": "rule",
        "llm_call_count": 0,
        "sink_writes": 0,
        "case_count": len(records),
        "vector_unavailable": vector_unavailable,
        "reranker_unavailable": reranker_unavailable,
        "stale_gold_count": len(stale_records),
        "stale_detection_miss_count": sum(
            1 for r in stale_records if r["dead_path_attribution"] == "detection_miss"
        ),
        "stale_routing_error_count": sum(
            1 for r in stale_records if r["dead_path_attribution"] == "routing_error"
        ),
        "stale_evidence_insufficient_count": sum(
            1 for r in stale_records if r["evidence_insufficient"]
        ),
        "stale_flagged_count": sum(
            1 for r in stale_records if r["proposed_action"] == "flag_stale"
        ),
        "over_escalation_count": len(over_records),
        "over_escalation_trigger_distribution": dict(
            sorted(Counter(r["escalate_trigger"] for r in over_records).items())
        ),
        "dead_path_decision": "fix_detection_3_3" if all(
            not r["stale_detected"] for r in stale_records
        ) else "fix_routing_3_4",
    }


def _markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# Q4-P1 Diagnostic (auto-generated companion)",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- created_at: `{summary['created_at']}`",
        f"- mode: {summary['mode']} "
        f"(controller={summary['controller']}, llm_calls=0, sink_writes=0)",
        f"- vector_unavailable: {summary['vector_unavailable']}",
        f"- stale_gold: {summary['stale_gold_count']} | detection_miss: "
        f"{summary['stale_detection_miss_count']} | "
        f"routing_error: {summary['stale_routing_error_count']}",
        f"- over_escalation_count: {summary['over_escalation_count']}",
        f"- dead_path_decision: `{summary['dead_path_decision']}`",
        "",
        "| case | gold_cond | gold_action | detected | ev | auth_actor | proposed "
        "| stale? | dead_path | over_esc | trigger |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in records:
        lines.append(
            f"| `{r['case_id']}` | {r['gold_condition']} | {r['gold_action']} | "
            f"`{','.join(r['detected_conditions']) or '-'}` | {r['evidence_decision']} | "
            f"{r['authorized_actor']} | {r['proposed_action']} | {r['stale_detected']} | "
            f"{r['dead_path_attribution'] or '-'} | {r['over_escalation']} | "
            f"{r['escalate_trigger'] or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
