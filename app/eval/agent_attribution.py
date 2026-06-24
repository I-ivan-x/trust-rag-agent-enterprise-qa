from __future__ import annotations

from typing import Any

AGENT_SYSTEMS = {"final_agentic_v2", "final_agentic_v2_llm"}
ACTION_TYPES = (
    "rewrite_query",
    "filtered_retrieval",
    "present_conflict_set",
    "refuse_with_explanation",
)
RETRIEVAL_ACTIONS = {"rewrite_query", "filtered_retrieval"}
RECOVERY_ACTIONS = {
    "rewrite_query",
    "filtered_retrieval",
    "present_conflict_set",
}


def compute_agent_attribution(
    trace_rows: list[dict[str, Any]],
    result_rows: list[Any],
) -> dict[str, Any] | None:
    agent_traces = [
        row
        for row in trace_rows
        if row.get("system_name") in AGENT_SYSTEMS
        and isinstance(row.get("action_trajectory"), list)
        and row.get("action_trajectory")
    ]
    if not agent_traces:
        return None

    grounded_by_key, grounded_by_case = _grounded_maps(result_rows)
    per_action = {
        action: {
            "trigger_count": 0,
            "accept_count": 0,
            "success_count": 0,
            "false_recovery_count": 0,
            "ineffective": 0,
        }
        for action in ACTION_TYPES
    }

    tf2_case_ids: set[str] = set()
    tf3_step_count = 0
    tf4_case_ids: set[str] = set()
    tf1_candidates: list[dict[str, Any]] = []
    llm_propose_count = 0
    llm_accept_count = 0
    llm_fallback_count = 0
    controller_by_system: dict[str, str] = {}

    for trace in agent_traces:
        case_id = str(trace.get("case_id") or "")
        system_name = str(trace.get("system_name") or "")
        if system_name:
            controller_by_system[system_name] = _controller_for_system(system_name)
        grounded = grounded_by_key.get(
            (case_id, system_name),
            grounded_by_case.get(case_id),
        )
        trajectory = trace.get("action_trajectory") or []
        last_sufficient_step: dict[str, Any] | None = None
        chosen_actions: list[str] = []
        unselected_recovery_actions: set[str] = set()

        for step in trajectory:
            legal_actions = _string_list(step.get("legal_actions"))
            chosen_action = _string_or_none(step.get("chosen_action"))
            chosen_source = _string_or_none(step.get("chosen_source"))
            fallback_reason = _string_or_none(step.get("fallback_reason"))
            validator_ok = step.get("validator_ok") is not False
            accepted = step.get("accepted", True) is True

            for action in ACTION_TYPES:
                if action in legal_actions:
                    per_action[action]["trigger_count"] += 1

            if chosen_action:
                chosen_actions.append(chosen_action)
                unselected_recovery_actions.update(
                    action
                    for action in legal_actions
                    if action != chosen_action and action in RECOVERY_ACTIONS
                )

            if (
                chosen_action in ACTION_TYPES
                and accepted
                and validator_ok
            ):
                per_action[chosen_action]["accept_count"] += 1

            if _is_llm_step(system_name, step):
                llm_propose_count += 1
                if chosen_source == "llm":
                    llm_accept_count += 1
                if chosen_source == "llm_fallback_rule" or fallback_reason:
                    llm_fallback_count += 1

            if _is_tf3(step):
                tf3_step_count += 1

            post_decision = _string_or_none(step.get("post_action_evidence_decision"))
            executed = bool(chosen_action in ACTION_TYPES and validator_ok)
            if executed and post_decision == "sufficient":
                last_sufficient_step = step
            if (
                executed
                and chosen_action in RETRIEVAL_ACTIONS
                and post_decision == "insufficient"
            ):
                per_action[chosen_action]["ineffective"] += 1
                if case_id:
                    tf2_case_ids.add(_case_key(case_id, system_name))

        terminal_reason = _string_or_none(trace.get("terminal_reason"))
        if terminal_reason == "budget_exhausted" and case_id:
            tf4_case_ids.add(_case_key(case_id, system_name))

        if last_sufficient_step is not None:
            action = _string_or_none(last_sufficient_step.get("chosen_action"))
            if action in ACTION_TYPES and grounded is True:
                per_action[action]["success_count"] += 1
            elif action in ACTION_TYPES and grounded is False:
                per_action[action]["false_recovery_count"] += 1

        if grounded is not True and unselected_recovery_actions:
            tf1_candidates.append(
                {
                    "case_id": case_id,
                    "system_name": system_name,
                    "chosen_actions": chosen_actions,
                    "unselected_legal_recovery_actions": sorted(
                        unselected_recovery_actions
                    ),
                    "requires_replay": True,
                }
            )

    controller: dict[str, Any] = {
        "by_system": dict(sorted(controller_by_system.items())),
    }
    if llm_propose_count > 0 or "final_agentic_v2_llm" in controller_by_system:
        controller.update(
            {
                "llm_propose_count": llm_propose_count,
                "llm_accept_count": llm_accept_count,
                "llm_fallback_count": llm_fallback_count,
                "llm_fallback_rate": (
                    llm_fallback_count / llm_propose_count
                    if llm_propose_count
                    else 0.0
                ),
            }
        )

    return {
        "agent_systems": sorted(controller_by_system),
        "per_action": per_action,
        "controller": controller,
        "trajectory_failures": {
            "tf2_ineffective_action_case_count": len(tf2_case_ids),
            "tf3_validator_reject_step_count": tf3_step_count,
            "tf4_budget_exhausted_case_count": len(tf4_case_ids),
            "tf1_candidate_count": len(tf1_candidates),
            "tf1_auto_hit_count": 0,
            "tf1_candidates": tf1_candidates,
        },
        "notes": {
            "counts_only": "Small-n agent attribution reports counts only, not rates.",
            "tf1_policy": "TF1 is not auto-scored in P3-06; candidates require replay.",
            "headline_policy": (
                "Agent attribution is diagnostic and is not merged into headline metrics."
            ),
        },
    }


def _grounded_maps(
    result_rows: list[Any],
) -> tuple[dict[tuple[str, str], bool | None], dict[str, bool | None]]:
    by_key: dict[tuple[str, str], bool | None] = {}
    by_case: dict[str, bool | None] = {}
    for row in result_rows:
        case_id = _string_or_none(_field(row, "case_id"))
        if not case_id:
            continue
        system_name = _string_or_none(_field(row, "system_name")) or ""
        grounded = _field(row, "grounded_correct")
        if grounded is not None and not isinstance(grounded, bool):
            grounded = bool(grounded)
        by_case[case_id] = grounded
        if system_name:
            by_key[(case_id, system_name)] = grounded
    return by_key, by_case


def _field(row: Any, name: str) -> Any:
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def _controller_for_system(system_name: str) -> str:
    return "llm" if system_name == "final_agentic_v2_llm" else "rule"


def _is_llm_step(system_name: str, step: dict[str, Any]) -> bool:
    return (
        system_name == "final_agentic_v2_llm"
        or step.get("controller_source") == "llm"
        or str(step.get("chosen_source") or "").startswith("llm")
        or step.get("fallback_reason") is not None
    )


def _is_tf3(step: dict[str, Any]) -> bool:
    fallback_reason = _string_or_none(step.get("fallback_reason"))
    return step.get("accepted") is False or bool(
        fallback_reason and fallback_reason.startswith("validator_reject")
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _case_key(case_id: str, system_name: str) -> str:
    return f"{system_name}:{case_id}" if system_name else case_id
