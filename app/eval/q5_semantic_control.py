"""Isolated fixed-table solvability diagnostic for Q5 protocol v3.

Execution receives only normal runtime inputs.  Sealed labels enter exclusively
in the grading function after all loop and outcome artifacts already exist.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.eval.q5_dataset import Q5EnvironmentStore
from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_outcome import Q5OutcomeEnvironmentState, grade_q5_final_state
from app.eval.q5_provenance import derive_q5_model_identity
from app.eval.q5_runner import Q5RuntimeCaseInput, _run_trial
from app.govern.q5_loop import Q5AgentSystem
from app.schemas.q5_task import Q5Gold, Q5TaskInput

Q5_SEMANTIC_TABLE_RULE_CONTROL = "q5_semantic_table_rule_control"


class Q5SemanticTableRuleModel(Q5DeterministicMockPolicyModel):
    """Three-family fixed state table over prompt-visible runtime facts only."""

    provider = "grader_only_fixed_table"
    model_name = "q5-semantic-table-rule-control-v1"


class Q5SemanticControlExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "q5-semantic-table-control-raw-v1"
    control: str = Q5_SEMANTIC_TABLE_RULE_CONTROL
    rows: list[dict[str, Any]] = Field(default_factory=list)


class Q5SemanticControlReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "q5-semantic-table-control-graded-v1"
    control: str = Q5_SEMANTIC_TABLE_RULE_CONTROL
    fixed_table_solvability: float
    semantic_trial_count: int = Field(ge=0)
    rows: list[dict[str, Any]] = Field(default_factory=list)


def execute_q5_semantic_table_rule_control(
    tasks: Sequence[Q5TaskInput],
    environment: Q5EnvironmentStore,
    runtime_cases: Mapping[str, Q5RuntimeCaseInput],
    *,
    k: int = 1,
) -> Q5SemanticControlExecution:
    """Run the control through the production loop, tools, validator, and sink."""

    if k < 1:
        raise ValueError("Q5 semantic-table control k must be positive")
    task_ids = {task.case_id for task in tasks}
    if task_ids != set(runtime_cases):
        raise ValueError("Q5 semantic-table runtime case matrix mismatch")
    rows: list[dict[str, Any]] = []
    for task in tasks:
        model = Q5SemanticTableRuleModel()
        identity = derive_q5_model_identity(model)
        for run_index in range(1, k + 1):
            trial = _run_trial(
                task=task,
                source_environment=environment[task.environment_ref],
                runtime_case=runtime_cases[task.case_id],
                system=Q5AgentSystem.llm,
                run_index=run_index,
                prepared_model=(model, identity),
            )
            rows.append(
                {
                    "case_id": task.case_id,
                    "run_index": run_index,
                    "result": trial["result"],
                    "environment_before": trial["environment_before"],
                    "environment_after": trial["environment_after"],
                    "tool_events": trial["tool_events"],
                    "trajectory": trial["trajectory"],
                }
            )
    return Q5SemanticControlExecution(rows=rows)


def grade_q5_semantic_table_rule_control(
    execution: Q5SemanticControlExecution,
    gold: Mapping[str, Q5Gold],
) -> Q5SemanticControlReport:
    """Grade sealed final state; never trust the control model's prose."""

    graded: list[dict[str, Any]] = []
    semantic_successes = 0
    semantic_trials = 0
    for row in execution.rows:
        case_id = str(row["case_id"])
        if case_id not in gold:
            raise ValueError(f"missing sealed gold for semantic control case: {case_id}")
        case_gold = gold[case_id]
        result = row["result"]
        before = Q5OutcomeEnvironmentState.model_validate(
            row["environment_before"]["environment"]
        )
        after = Q5OutcomeEnvironmentState.model_validate(
            row["environment_after"]["environment"]
        )
        final_state = grade_q5_final_state(
            case_gold.final_state_assertions,
            before=before,
            after=after,
        )
        completed_tools = {
            str(event.get("tool_name"))
            for event in row["tool_events"]
            if event.get("status") in {"ok", "not_found"}
        }
        required = set(case_gold.required_observations)
        qualified = bool(final_state.task_success and required <= completed_tools)
        if case_gold.stratum.value == "semantic":
            semantic_trials += 1
            semantic_successes += int(qualified)
        graded.append(
            {
                "case_id": case_id,
                "run_index": int(row["run_index"]),
                "stratum": case_gold.stratum.value,
                "final_action": result["final_action"],
                "task_success": final_state.task_success,
                "trajectory_qualified_success": qualified,
                "completed_observations": sorted(completed_tools),
                "llm_calls": result["llm_calls"],
                "total_tokens": result["total_tokens"],
            }
        )
    return Q5SemanticControlReport(
        fixed_table_solvability=(
            round(semantic_successes / semantic_trials, 6)
            if semantic_trials
            else 0.0
        ),
        semantic_trial_count=semantic_trials,
        rows=graded,
    )
