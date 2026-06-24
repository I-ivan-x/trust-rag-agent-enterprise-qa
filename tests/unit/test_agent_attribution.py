from __future__ import annotations

from pathlib import Path

import app.eval.runner as runner
from app.core.enums import EvalSplit
from app.eval.agent_attribution import compute_agent_attribution
from app.eval.report import write_eval_report
from app.llm.usage import LLMUsageTotals
from app.schemas.eval import EvalResult


def test_agent_attribution_counts_trigger_accept_success_and_false_recovery() -> None:
    attribution = compute_agent_attribution(
        [
            _trace(
                "case-success",
                [
                    _step(
                        legal=["rewrite_query", "filtered_retrieval"],
                        chosen="filtered_retrieval",
                        post="sufficient",
                    )
                ],
            ),
            _trace(
                "case-false",
                [
                    _step(
                        legal=["filtered_retrieval"],
                        chosen="filtered_retrieval",
                        post="sufficient",
                    )
                ],
            ),
        ],
        [
            _result("case-success", grounded=True),
            _result("case-false", grounded=False),
        ],
    )

    assert attribution is not None
    per_action = attribution["per_action"]
    assert per_action["rewrite_query"]["trigger_count"] == 1
    assert per_action["filtered_retrieval"]["trigger_count"] == 2
    assert per_action["filtered_retrieval"]["accept_count"] == 2
    assert per_action["filtered_retrieval"]["success_count"] == 1
    assert per_action["filtered_retrieval"]["false_recovery_count"] == 1


def test_agent_attribution_ineffective_action_counts_tf2_case() -> None:
    attribution = compute_agent_attribution(
        [
            _trace(
                "case-ineffective",
                [_step(chosen="rewrite_query", post="insufficient")],
            )
        ],
        [_result("case-ineffective", grounded=False)],
    )

    assert attribution is not None
    assert attribution["per_action"]["rewrite_query"]["ineffective"] == 1
    assert (
        attribution["trajectory_failures"]["tf2_ineffective_action_case_count"] == 1
    )


def test_agent_attribution_tf3_counts_rejected_llm_step() -> None:
    attribution = compute_agent_attribution(
        [
            _trace(
                "case-rejected",
                [
                    _step(
                        chosen="filtered_retrieval",
                        controller_source="llm",
                        chosen_source="llm_fallback_rule",
                        accepted=False,
                        fallback_reason="validator_reject:status_filter_must_only_allow_active",
                    )
                ],
                system_name="final_agentic_v2_llm",
            )
        ],
        [_result("case-rejected", grounded=False, system_name="final_agentic_v2_llm")],
    )

    assert attribution is not None
    failures = attribution["trajectory_failures"]
    controller = attribution["controller"]
    assert failures["tf3_validator_reject_step_count"] == 1
    assert controller["llm_propose_count"] == 1
    assert controller["llm_accept_count"] == 0
    assert controller["llm_fallback_count"] == 1
    assert controller["llm_fallback_rate"] == 1.0
    assert attribution["per_action"]["filtered_retrieval"]["accept_count"] == 1


def test_agent_attribution_tf4_counts_budget_exhaustion() -> None:
    attribution = compute_agent_attribution(
        [
            _trace(
                "case-budget",
                [_step(chosen="rewrite_query", post="insufficient")],
                terminal_reason="budget_exhausted",
            )
        ],
        [_result("case-budget", grounded=False)],
    )

    assert attribution is not None
    assert (
        attribution["trajectory_failures"]["tf4_budget_exhausted_case_count"] == 1
    )


def test_agent_attribution_tf1_is_candidate_only() -> None:
    attribution = compute_agent_attribution(
        [
            _trace(
                "case-candidate",
                [
                    _step(
                        legal=["rewrite_query", "filtered_retrieval"],
                        chosen="rewrite_query",
                        post="insufficient",
                    )
                ],
            )
        ],
        [_result("case-candidate", grounded=False)],
    )

    assert attribution is not None
    failures = attribution["trajectory_failures"]
    assert failures["tf1_candidate_count"] == 1
    assert failures["tf1_auto_hit_count"] == 0
    candidate = failures["tf1_candidates"][0]
    assert candidate["requires_replay"] is True
    assert candidate["unselected_legal_recovery_actions"] == ["filtered_retrieval"]


def test_non_agent_run_has_no_attribution() -> None:
    assert (
        compute_agent_attribution(
            [
                _trace(
                    "case-final",
                    [_step()],
                    system_name="final_agentic",
                )
            ],
            [_result("case-final", grounded=True, system_name="final_agentic")],
        )
        is None
    )


def test_runner_summary_adds_attribution_for_agentic_v2() -> None:
    summary = runner._build_summary(
        run_id="agent-attribution",
        systems=["final_agentic_v2"],
        eval_split=EvalSplit.fixture,
        cases=[object()],
        results=[_result("case-summary", grounded=True)],
        trace_rows=[
            _trace(
                "case-summary",
                [_step(chosen="filtered_retrieval", post="sufficient")],
            )
        ],
        audit_rows=[],
        unavailable_systems={},
        full_case_count=1,
        case_selection={"limit": None, "case_id": None, "max_cases": None},
        mock_run=True,
        retrieval_only=False,
        real_run=False,
        reranker_unavailable_any=False,
        run_dir=Path("data/eval_runs/agent-attribution"),
        usage=LLMUsageTotals(),
    )

    assert "agent_attribution" in summary
    metrics = summary["agent_attribution"]["per_action"]["filtered_retrieval"]
    assert metrics["success_count"] == 1
    assert {
        "trigger_count",
        "accept_count",
        "success_count",
        "false_recovery_count",
    } <= set(metrics)


def test_eval_report_renders_agent_attribution_section(tmp_path: Path) -> None:
    path = tmp_path / "EVALUATION_REPORT.md"
    write_eval_report(
        path,
        {
            "run_id": "report",
            "systems": ["final_agentic_v2_llm"],
            "agent_attribution": {
                "per_action": {
                    "rewrite_query": _metrics(),
                    "filtered_retrieval": _metrics(success_count=1),
                    "present_conflict_set": _metrics(),
                    "refuse_with_explanation": _metrics(),
                },
                "trajectory_failures": {
                    "tf2_ineffective_action_case_count": 1,
                    "tf3_validator_reject_step_count": 1,
                    "tf4_budget_exhausted_case_count": 0,
                    "tf1_candidate_count": 1,
                    "tf1_auto_hit_count": 0,
                },
                "controller": {
                    "llm_propose_count": 2,
                    "llm_accept_count": 1,
                    "llm_fallback_count": 1,
                    "llm_fallback_rate": 0.5,
                },
            },
        },
    )

    rendered = path.read_text(encoding="utf-8")
    assert "## Agent Attribution" in rendered
    assert "false_recovery_count" in rendered
    assert "TF1 replay candidates" in rendered
    assert "llm_fallback_rate" in rendered


def _trace(
    case_id: str,
    trajectory: list[dict],
    *,
    system_name: str = "final_agentic_v2",
    terminal_reason: str = "answer",
) -> dict:
    return {
        "case_id": case_id,
        "system_name": system_name,
        "action_trajectory": trajectory,
        "terminal_reason": terminal_reason,
        "budget_consumed": len(trajectory),
    }


def _step(
    *,
    legal: list[str] | None = None,
    chosen: str = "filtered_retrieval",
    accepted: bool = True,
    validator_ok: bool = True,
    post: str = "insufficient",
    controller_source: str = "rule",
    chosen_source: str | None = None,
    fallback_reason: str | None = None,
) -> dict:
    return {
        "step": 1,
        "diagnosis_failure_type": "POLICY_CROWDING",
        "legal_actions": legal or ["filtered_retrieval", "refuse_with_explanation"],
        "controller_source": controller_source,
        "chosen_action": chosen,
        "chosen_source": chosen_source or controller_source,
        "accepted": accepted,
        "fallback_reason": fallback_reason,
        "validator_ok": validator_ok,
        "post_action_evidence_decision": post,
        "reason": None,
    }


def _result(
    case_id: str,
    *,
    grounded: bool,
    system_name: str = "final_agentic_v2",
) -> EvalResult:
    return EvalResult(
        case_id=case_id,
        system_name=system_name,
        eval_split=EvalSplit.fixture,
        corpus_source="synthetic_fixture",
        raw_correct=grounded,
        grounded_correct=grounded,
        citation_valid=True,
        refused=False,
        metrics={},
    )


def _metrics(**overrides: int) -> dict:
    metrics = {
        "trigger_count": 0,
        "accept_count": 0,
        "success_count": 0,
        "false_recovery_count": 0,
        "ineffective": 0,
    }
    metrics.update(overrides)
    return metrics
