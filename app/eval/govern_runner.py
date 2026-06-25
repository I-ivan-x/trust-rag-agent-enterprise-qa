from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.eval.govern_attribution import compute_governance_attribution
from app.eval.govern_metrics import SIDE_EFFECT_ACTIONS, compute_governance_metrics
from app.eval.passk import compute_govern_passk
from app.govern.conditions import ActorContext, GovernanceAction, detect_conditions
from app.govern.governor import govern
from app.govern.sinks import ActionRecord, ActionSink, LocalJsonlSink
from app.guards.evidence_gate import EvidenceGateConfig, evidence_gate_config_from_settings
from app.schemas.eval import EvalCase
from app.schemas.retrieval import RetrievalOptions
from app.workflow.orchestrator import run_trust_gated_pass
from app.workflow.state import RetrievalPassResult

GOVERN_SYSTEMS = {"final_governed_rule", "final_governed_llm"}
REAL_RUN_OPTIONS = RetrievalOptions(
    top_k_dense=20,
    top_k_sparse=20,
    top_n_rerank=8,
    return_trace=True,
)


def run_governance_case(
    case: EvalCase,
    controller,
    retriever,
    reranker,
    settings=None,
    *,
    system_name: str,
    run_index: int,
    evidence_gate_config: EvidenceGateConfig | None = None,
    retrieval_options: RetrievalOptions | None = None,
    sink: ActionSink | None = None,
    sink_root: Path | None = None,
) -> dict[str, Any]:
    """Run one Q3 governance case and return P6-compatible result/trace rows."""

    if sink is not None:
        return _run_governance_case_with_sink(
            case,
            controller,
            retriever,
            reranker,
            settings,
            system_name=system_name,
            run_index=run_index,
            evidence_gate_config=evidence_gate_config,
            retrieval_options=retrieval_options,
            sink=sink,
        )
    if sink_root is not None:
        return _run_governance_case_with_sink(
            case,
            controller,
            retriever,
            reranker,
            settings,
            system_name=system_name,
            run_index=run_index,
            evidence_gate_config=evidence_gate_config,
            retrieval_options=retrieval_options,
            sink=LocalJsonlSink(sink_root),
        )
    with tempfile.TemporaryDirectory(prefix="q3-governance-sink-") as tmp_dir:
        return _run_governance_case_with_sink(
            case,
            controller,
            retriever,
            reranker,
            settings,
            system_name=system_name,
            run_index=run_index,
            evidence_gate_config=evidence_gate_config,
            retrieval_options=retrieval_options,
            sink=LocalJsonlSink(Path(tmp_dir)),
        )


def build_governance_summary(
    *,
    run_id: str,
    run_dir: Path,
    systems: list[str],
    result_rows: list[dict[str, Any]],
    trace_rows: list[dict[str, Any]],
    k: int,
    real_run: bool,
    mock_used: bool,
    vector_unavailable: bool = False,
    reranker_unavailable: bool = False,
    index_summaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metrics = compute_governance_metrics(result_rows)
    attribution = compute_governance_attribution(trace_rows, result_rows) or {
        "failure_taxonomy": {},
        "per_action": {},
    }
    passk = compute_govern_passk(result_rows, k=k)
    eligible_by_system = compute_governance_headline_eligibility(
        metrics,
        attribution,
        real_run=real_run,
        mock_used=mock_used,
    )
    return {
        "run_id": run_id,
        "systems": systems,
        "mode": "real_run" if real_run else "mock_governance",
        "k": k,
        "attempt_count": len(result_rows),
        "case_count": len({(row.get("split"), row.get("case_id")) for row in result_rows}),
        "real_run": real_run,
        "mock_used": mock_used,
        "vector_unavailable": vector_unavailable,
        "reranker_unavailable": reranker_unavailable,
        "governance_metrics": metrics,
        "governance_attribution": attribution,
        "governance_passk": passk,
        "governance_headline_eligible": bool(
            eligible_by_system and all(eligible_by_system.values())
        ),
        "governance_headline_eligible_by_system": eligible_by_system,
        "headline_policy": (
            "Governance action metrics are action_metric diagnostics and are never "
            "merged into grounded retrieval/answer headline metrics."
        ),
        "index_summaries": index_summaries or [],
        "run_dir": run_dir.as_posix(),
    }


def compute_governance_headline_eligibility(
    governance_metrics: dict[str, Any],
    governance_attribution: dict[str, Any] | None,
    *,
    real_run: bool,
    mock_used: bool,
) -> dict[str, bool]:
    failures = (governance_attribution or {}).get("failure_taxonomy") or {}
    guarded = (
        int(failures.get("F11_action_without_evidence", 0)) == 0
        and int(failures.get("F13_missed_escalation_unauth", 0)) == 0
    )
    by_system = governance_metrics.get("by_system") or {}
    return {
        system_name: bool(
            real_run
            and not mock_used
            and guarded
            and system_metrics.get("anti_gaming_triad_ok") is True
        )
        for system_name, system_metrics in sorted(by_system.items())
    }


def governance_failure_rows(result_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for row in result_rows:
        reasons = []
        if row.get("proposed_action") != row.get("gold_action"):
            reasons.append("action_mismatch")
        if row.get("evidence_decision") == "insufficient" and row.get("executed_side_effect"):
            reasons.append("F11_action_without_evidence")
        if row.get("authorized") is False and row.get("executed_side_effect"):
            reasons.append("F13_missed_escalation_unauth")
        if reasons:
            failures.append(
                {
                    "case_id": row.get("case_id"),
                    "system_name": row.get("system_name"),
                    "run_index": row.get("run_index"),
                    "split": row.get("split"),
                    "reasons": reasons,
                    "gold_action": row.get("gold_action"),
                    "proposed_action": row.get("proposed_action"),
                    "executed_side_effect": row.get("executed_side_effect"),
                }
            )
    return failures


def _run_governance_case_with_sink(
    case: EvalCase,
    controller,
    retriever,
    reranker,
    settings,
    *,
    system_name: str,
    run_index: int,
    evidence_gate_config: EvidenceGateConfig | None,
    retrieval_options: RetrievalOptions | None,
    sink: ActionSink,
) -> dict[str, Any]:
    settings = settings or get_settings()
    gate_config = evidence_gate_config or evidence_gate_config_from_settings(settings)
    pass_result = run_trust_gated_pass(
        query=case.query,
        retrieval_options=retrieval_options or REAL_RUN_OPTIONS,
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
    outcome = govern(report, pass_result, actor, controller, sink)
    result_row = _result_row(
        case=case,
        system_name=system_name,
        run_index=run_index,
        report=report,
        outcome=outcome,
    )
    trace_row = _trace_row(
        case=case,
        system_name=system_name,
        run_index=run_index,
        actor=actor,
        pass_result=pass_result,
        result_row=result_row,
        outcome_trace=outcome.trace,
        record=outcome.record,
    )
    return {"result": result_row, "trace": trace_row}


def _requested_action(case: EvalCase) -> GovernanceAction | None:
    query = case.query.lower()
    if any(term in query for term in ("告警", "alert", "运维频道")):
        return GovernanceAction.send_alert
    if any(term in query for term in ("工单", "整改", "remediation ticket", "ticket")):
        return GovernanceAction.open_remediation_ticket
    if any(term in query for term in ("现行", "stale", "deprecated", "过期")):
        return GovernanceAction.flag_stale

    try:
        gold_action = GovernanceAction(str(case.gold_action))
    except ValueError:
        return None
    if gold_action in {
        GovernanceAction.flag_stale,
        GovernanceAction.open_remediation_ticket,
        GovernanceAction.send_alert,
    }:
        return gold_action
    return None


def _result_row(
    *,
    case: EvalCase,
    system_name: str,
    run_index: int,
    report,
    outcome,
) -> dict[str, Any]:
    record = outcome.record
    proposed_action = str(outcome.trace.get("proposed_action") or outcome.proposal.action.value)
    approval_state = record.approval_state if record is not None else "none"
    executed_side_effect = _executed_side_effect(record)
    forced_action = (
        outcome.validation.forced_action.value
        if outcome.validation.forced_action is not None
        else None
    )
    risk_tier = outcome.trace.get("risk_tier")
    if risk_tier is None and proposed_action == GovernanceAction.no_op.value:
        risk_tier = "none"
    return {
        "case_id": case.case_id,
        "system_name": system_name,
        "run_index": run_index,
        "split": case.eval_split.value,
        "gold_action": case.gold_action,
        "gold_condition": case.gold_condition,
        "secondary_conditions": case.secondary_conditions,
        "authorized": (
            case.authorized if case.authorized is not None else report.authorized_actor
        ),
        "expected_tier": case.expected_tier,
        "gold_doc_ids": case.gold_doc_ids,
        "detected_conditions": [condition.value for condition in report.conditions],
        "authorized_actor": report.authorized_actor,
        "evidence_decision": report.evidence_decision,
        "proposed_action": proposed_action,
        "controller_source": outcome.proposal.source,
        "risk_tier": risk_tier,
        "validator_ok": outcome.validation.ok,
        "forced_action": forced_action if not outcome.validation.ok else None,
        "approval_state": approval_state,
        "executed_side_effect": executed_side_effect,
        "sink_record_id": record.record_id if record is not None else None,
    }


def _trace_row(
    *,
    case: EvalCase,
    system_name: str,
    run_index: int,
    actor: ActorContext,
    pass_result: RetrievalPassResult,
    result_row: dict[str, Any],
    outcome_trace: dict[str, Any],
    record: ActionRecord | None,
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "system_name": system_name,
        "run_index": run_index,
        "split": case.eval_split.value,
        "query": case.query,
        "user_role": case.user_role,
        "requested_action": (
            actor.requested_action.value if actor.requested_action is not None else None
        ),
        "retrieved_chunk_ids": [
            result.chunk.chunk_id for result in pass_result.reranked_chunks
        ],
        "surviving_chunk_ids": [
            result.chunk.chunk_id for result in pass_result.acl_decision.surviving_chunks
        ],
        "blocked_chunk_ids": [
            result.chunk.chunk_id for result in pass_result.acl_decision.blocked_chunks
        ],
        "result_contract": result_row,
        "conditions": outcome_trace.get("conditions", []),
        "proposed_action": outcome_trace.get("proposed_action"),
        "validator_verdict": outcome_trace.get("validator_verdict"),
        "forced": outcome_trace.get("forced"),
        "approval_state": outcome_trace.get("approval_state"),
        "sink_record_id": outcome_trace.get("sink_record_id"),
        "governance_trace": outcome_trace,
        "sink_record": record.model_dump(mode="json") if record is not None else None,
        "warnings": pass_result.warnings,
    }


def _executed_side_effect(record: ActionRecord | None) -> bool:
    if record is None:
        return False
    return record.approval_state == "committed" and record.action.value in SIDE_EFFECT_ACTIONS


def _clearance_value(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "value", str(value))
