"""Hash-closed strong symbolic Q5 control with a Gold-isolated runtime."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.eval.q5_dataset import (
    Q5EnvironmentStore,
    load_q5_gold,
    load_q5_runtime_dataset,
)
from app.eval.q5_outcome import Q5OutcomeEnvironmentState, grade_q5_final_state
from app.eval.q5_pairs import compute_q5_crossed_pair_metrics
from app.eval.q5_provenance import q5_read_json, q5_read_jsonl, q5_sha256_file
from app.eval.q5_runner import Q5RuntimeCaseInput, _run_trial, load_q5_runtime_cases
from app.govern.conditions import GovernanceAction
from app.govern.q5_context import (
    Q5_ACTION_TO_DISPOSITION,
    Q5DecisionBasis,
    Q5DecisionContext,
    Q5ProposalKind,
    Q5StructuredProposal,
)
from app.govern.q5_loop import Q5AgentSystem
from app.govern.q5_policy import Q5PolicyStep
from app.govern.q5_rule_policy import q5_fixed_table_runtime_proposal
from app.schemas.q5_task import Q5Gold, Q5TaskInput

Q5_SYMBOLIC_ROWS_SCHEMA = "q5-strong-symbolic-rows-v2"
Q5_SYMBOLIC_SUMMARY_SCHEMA = "q5-strong-symbolic-summary-v2"
Q5_SYMBOLIC_HASHES_SCHEMA = "q5-strong-symbolic-hashes-v2"
Q5_SYMBOLIC_V1_HASHES_SCHEMA = "q5-strong-symbolic-hashes-v1"
Q5_SYMBOLIC_FILES = frozenset(
    {
        "symbolic_rows.jsonl",
        "symbolic_summary.json",
        "symbolic_report.md",
        "symbolic_hashes.json",
    }
)

# Frozen generic semantic vocabulary. It contains no resource, policy, case, or label ID.
_DISPOSITION_LEXICON: Mapping[str, tuple[str, ...]] = {
    "human_review": ("human review", "ownership review", "archival review"),
    "remediate": ("remediation ticket", "remediation"),
    "mark_stale": ("marks the runbook stale", "makes the runbook stale"),
    "notify": ("requires an alert", "pages on", "requires alert"),
    "no_action": ("no action", "suppresses"),
}
_SUCCESS_STATUSES = frozenset({"ok", "not_found"})
_FROZEN_SYMBOLIC_V1_ARTIFACTS = {
    "symbolic_report.md": "074072baa17cf52feae76e3dd2014b16bf4ecf71a8765457311bfedb28421872",
    "symbolic_rows.jsonl": "da9c907d342d5c7d1538e419574699b58441e336620ae5e452cbef01a2efba11",
    "symbolic_summary.json": "2dac48d1d63083edc3dbdf54cb4c2bedfe28ec15babfa633e2a7ce878c777f6f",
}
_SYMBOLIC_SOURCE_DEPENDENCIES = (
    "app/schemas/q5_task.py",
    "app/eval/q5_dataset.py",
    "app/eval/q5_symbolic_control.py",
    "app/eval/q5_runner.py",
    "app/eval/q5_outcome.py",
    "app/eval/q5_pairs.py",
    "app/eval/q5_provenance.py",
    "app/govern/conditions.py",
    "app/govern/executor.py",
    "app/govern/sinks.py",
    "app/govern/validator.py",
    "app/govern/q5_loop.py",
    "app/govern/q5_policy.py",
    "app/govern/q5_rule_policy.py",
    "app/govern/q5_context.py",
    "app/govern/q5_environment.py",
    "app/govern/q5_fallback.py",
    "app/govern/q5_tool_validator.py",
    "app/govern/q5_tools.py",
)


class Q5StrongSymbolicPolicy:
    """Generic clause/state matcher using only the normal decision context."""

    policy_source = "rule"

    def decide(self, context: Q5DecisionContext) -> Q5PolicyStep:
        fixed = q5_fixed_table_runtime_proposal(context)
        if fixed.kind is Q5ProposalKind.observe or not context.observations:
            proposal = fixed
        else:
            proposal = self._semantic_terminal(context) or self._safe_terminal(context)
        return Q5PolicyStep(
            proposal=proposal,
            policy_source="rule",
            parse_status="accepted",
            llm_called=False,
        )

    def _semantic_terminal(
        self,
        context: Q5DecisionContext,
    ) -> Q5StructuredProposal | None:
        observation = next(
            (
                item
                for item in reversed(context.observations)
                if item.status in _SUCCESS_STATUSES and item.observation
            ),
            None,
        )
        if observation is None:
            return None
        status = str(observation.observation.get("status", "")).lower()
        scope = str(observation.observation.get("scope", "")).lower() or None
        requested_scope = _requested_scope(context.query)
        matches: list[tuple[str, str]] = []
        for evidence in context.authorized_evidence:
            disposition = q5_symbolic_policy_match(
                evidence.text_excerpt,
                status=status,
                observed_scope=scope,
                requested_scope=requested_scope,
            )
            if disposition is not None:
                matches.append((evidence.chunk_id, disposition))
        if not matches:
            return None
        dispositions = {item[1] for item in matches}
        if len(dispositions) != 1:
            return self._safe_terminal(context, observation.request_id)
        disposition_name = next(iter(dispositions))
        action = {
            "mark_stale": GovernanceAction.flag_stale,
            "remediate": GovernanceAction.open_remediation_ticket,
            "notify": GovernanceAction.send_alert,
            "human_review": GovernanceAction.escalate_to_human,
            "no_action": GovernanceAction.no_op,
        }[disposition_name]
        if action not in context.legal_terminal_actions:
            return self._safe_terminal(context, observation.request_id)
        evidence_id = matches[0][0]
        return Q5StructuredProposal(
            kind=Q5ProposalKind.terminal,
            action=action,
            decision_basis=Q5DecisionBasis(
                policy_disposition=Q5_ACTION_TO_DISPOSITION[action],
                evidence_chunk_id=evidence_id,
                observation_request_id=observation.request_id,
            ),
            disposition_source="rule",
            evidence_chunk_ids=[evidence_id],
            reason_code="symbolic_policy_binding",
            reason_summary="Observed state was matched to one authorized policy clause.",
        )

    def _safe_terminal(
        self,
        context: Q5DecisionContext,
        request_id: str | None = None,
    ) -> Q5StructuredProposal:
        action = GovernanceAction.escalate_to_human
        if action not in context.legal_terminal_actions:
            return q5_fixed_table_runtime_proposal(context)
        evidence_ids = [item.chunk_id for item in context.authorized_evidence[:1]]
        grounded = bool(evidence_ids and request_id)
        return Q5StructuredProposal(
            kind=Q5ProposalKind.terminal,
            action=action,
            decision_basis=(
                Q5DecisionBasis(
                    policy_disposition=Q5_ACTION_TO_DISPOSITION[action],
                    evidence_chunk_id=evidence_ids[0],
                    observation_request_id=request_id,
                )
                if grounded
                else None
            ),
            disposition_source="rule" if grounded else "fallback",
            evidence_chunk_ids=evidence_ids,
            reason_code="symbolic_ambiguity_safe_escalation",
            reason_summary="Policy matching was unknown or ambiguous; human review is required.",
        )


def execute_q5_strong_symbolic_control(
    tasks: Sequence[Q5TaskInput],
    environment: Q5EnvironmentStore,
    runtime_cases: Mapping[str, Q5RuntimeCaseInput],
    *,
    k: int = 3,
) -> list[dict[str, Any]]:
    """Execute the symbolic policy before any sealed labels are available."""

    if k != 3 or len(tasks) != 36 or set(runtime_cases) != {task.case_id for task in tasks}:
        raise ValueError("Q5 strong symbolic control requires the complete 36x3 matrix")
    policy = Q5StrongSymbolicPolicy()
    rows: list[dict[str, Any]] = []
    for task in tasks:
        for run_index in range(1, k + 1):
            trial = _run_trial(
                task=task,
                source_environment=environment[task.environment_ref],
                runtime_case=runtime_cases[task.case_id],
                system=Q5AgentSystem.rule,
                run_index=run_index,
                prepared_model=None,
                rule_policy=policy,
            )
            rows.append(
                {
                    "case_id": task.case_id,
                    "run_index": run_index,
                    "result": trial["result"],
                    "environment_before": trial["environment_before"],
                    "environment_after": trial["environment_after"],
                    "tool_events": trial["tool_events"],
                    "policy_events": trial["policy_events"],
                    "trajectory": trial["trajectory"],
                }
            )
    return rows


def grade_q5_strong_symbolic_control(
    rows: Sequence[Mapping[str, Any]],
    gold: Mapping[str, Q5Gold],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply sealed final-state and pair labels after runtime execution."""

    expected = {
        (case_id, run_index)
        for case_id in gold
        for run_index in range(1, 4)
    }
    seen: set[tuple[str, int]] = set()
    graded: list[dict[str, Any]] = []
    for raw in rows:
        case_id = str(raw.get("case_id") or "")
        run_index = int(raw.get("run_index") or 0)
        key = (case_id, run_index)
        if key not in expected or key in seen:
            raise ValueError("Q5 symbolic control has duplicate or extra runtime rows")
        seen.add(key)
        case_gold = gold[case_id]
        before = Q5OutcomeEnvironmentState.model_validate(
            raw["environment_before"]["environment"]
        )
        after = Q5OutcomeEnvironmentState.model_validate(
            raw["environment_after"]["environment"]
        )
        final_state = grade_q5_final_state(
            case_gold.final_state_assertions,
            before=before,
            after=after,
        )
        completed = {
            str(event.get("tool_name"))
            for event in raw["tool_events"]
            if event.get("status") in _SUCCESS_STATUSES
        }
        qualified = bool(
            final_state.task_success
            and set(case_gold.required_observations) <= completed
        )
        result = raw["result"]
        graded.append(
            {
                "schema_version": Q5_SYMBOLIC_ROWS_SCHEMA,
                "case_id": case_id,
                "run_index": run_index,
                "stratum": case_gold.stratum.value,
                "within_policy_group": _gold_tag(case_gold, "within_policy_group_"),
                "cross_policy_group": _gold_tag(case_gold, "cross_policy_group_"),
                "final_action": result["final_action"],
                "task_success": final_state.task_success,
                "trajectory_qualified_success": qualified,
                "completed_observations": sorted(completed),
                "llm_calls": result["llm_calls"],
                "total_tokens": result["total_tokens"],
            }
        )
    if seen != expected:
        raise ValueError("Q5 symbolic control runtime matrix is incomplete")
    semantic = [row for row in graded if row["stratum"] == "semantic"]
    pair = compute_q5_crossed_pair_metrics(graded, k=3)
    summary = {
        "schema_version": Q5_SYMBOLIC_SUMMARY_SCHEMA,
        "row_count": len(graded),
        "semantic_trial_count": len(semantic),
        "semantic_successes": sum(row["trajectory_qualified_success"] for row in semantic),
        "semantic_success": round(
            sum(row["trajectory_qualified_success"] for row in semantic) / len(semantic),
            6,
        ),
        "within_policy_pair_success": pair["within_policy_pair_success"],
        "within_policy_paired_count": pair["within_policy_paired_count"],
        "within_policy_failure_case_ids": pair["within_policy_failure_case_ids"],
        "cross_policy_pair_success": pair["cross_policy_pair_success"],
        "cross_policy_paired_count": pair["cross_policy_paired_count"],
        "cross_policy_failure_case_ids": pair["cross_policy_failure_case_ids"],
        "llm_calls": sum(int(row["llm_calls"]) for row in graded),
        "total_tokens": sum(int(row["total_tokens"]) for row in graded),
        "config_sha256": _config_sha256(),
        "implementation_sha256": hashlib.sha256(
            (
                inspect.getsource(Q5StrongSymbolicPolicy)
                + inspect.getsource(q5_symbolic_policy_match)
                + inspect.getsource(_clause_matches_state)
                + inspect.getsource(_dispositions)
            ).encode()
        ).hexdigest(),
        "implementation_sha256_scope": "policy_class_and_matcher_core_only",
        "source_attestation_scope": "entire_file_and_execution_dependencies",
        "source_file_sha256": _source_inventory()[
            "app/eval/q5_symbolic_control.py"
        ],
        "source_dependency_sha256": _source_inventory(),
        "control_kind": "frozen_closed_vocabulary_parser",
        "claim_scope": (
            "v4_benchmark_does_not_support_llm_necessity;"
            "not_general_natural_language_rule_solving"
        ),
    }
    return graded, summary


def build_q5_strong_symbolic_artifacts(
    *,
    tasks_path: Path | str,
    environment_path: Path | str,
    runtime_cases_path: Path | str,
    gold_path: Path | str,
    output_dir: Path | str,
) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(f"Q5 symbolic output already exists: {target}")
    dataset = load_q5_runtime_dataset(tasks_path, environment_path)
    runtime_cases = load_q5_runtime_cases(runtime_cases_path)
    runtime_rows = execute_q5_strong_symbolic_control(
        dataset.tasks,
        dataset.environment,
        runtime_cases,
    )
    gold = load_q5_gold(gold_path)
    rows, summary = grade_q5_strong_symbolic_control(runtime_rows, gold)
    summary["input_sha256"] = {
        "tasks": q5_sha256_file(Path(tasks_path)),
        "environment": q5_sha256_file(Path(environment_path)),
        "runtime_cases": q5_sha256_file(Path(runtime_cases_path)),
        "gold": q5_sha256_file(Path(gold_path)),
    }
    report = _render_report(summary)
    target.mkdir(parents=True)
    _write_jsonl(target / "symbolic_rows.jsonl", rows)
    _write_json(target / "symbolic_summary.json", summary)
    (target / "symbolic_report.md").write_text(report, encoding="utf-8")
    _write_json(
        target / "symbolic_hashes.json",
        {
            "schema_version": Q5_SYMBOLIC_HASHES_SCHEMA,
            "artifacts": {
                name: q5_sha256_file(target / name)
                for name in sorted(Q5_SYMBOLIC_FILES - {"symbolic_hashes.json"})
            },
        },
    )
    return verify_q5_strong_symbolic_artifacts(
        tasks_path=tasks_path,
        environment_path=environment_path,
        runtime_cases_path=runtime_cases_path,
        gold_path=gold_path,
        output_dir=target,
    )


def verify_q5_strong_symbolic_artifacts(
    *,
    tasks_path: Path | str,
    environment_path: Path | str,
    runtime_cases_path: Path | str,
    gold_path: Path | str,
    output_dir: Path | str,
) -> dict[str, Any]:
    target = Path(output_dir)
    actual = {path.name for path in target.iterdir()}
    if actual != Q5_SYMBOLIC_FILES:
        raise ValueError("Q5 symbolic artifact closure mismatch")
    hashes = q5_read_json(target / "symbolic_hashes.json")
    if hashes.get("schema_version") == Q5_SYMBOLIC_V1_HASHES_SCHEMA:
        return _verify_frozen_symbolic_v1(
            tasks_path=tasks_path,
            environment_path=environment_path,
            runtime_cases_path=runtime_cases_path,
            gold_path=gold_path,
            target=target,
            hashes=hashes,
        )
    if (
        hashes.get("schema_version") != Q5_SYMBOLIC_HASHES_SCHEMA
        or set(hashes.get("artifacts") or {})
        != Q5_SYMBOLIC_FILES - {"symbolic_hashes.json"}
    ):
        raise ValueError("Q5 symbolic hash inventory is invalid")
    for name, expected_hash in hashes["artifacts"].items():
        if q5_sha256_file(target / name) != expected_hash:
            raise ValueError(f"Q5 symbolic artifact hash mismatch: {name}")
    dataset = load_q5_runtime_dataset(tasks_path, environment_path)
    runtime_rows = execute_q5_strong_symbolic_control(
        dataset.tasks,
        dataset.environment,
        load_q5_runtime_cases(runtime_cases_path),
    )
    rows, summary = grade_q5_strong_symbolic_control(
        runtime_rows,
        load_q5_gold(gold_path),
    )
    summary["input_sha256"] = {
        "tasks": q5_sha256_file(Path(tasks_path)),
        "environment": q5_sha256_file(Path(environment_path)),
        "runtime_cases": q5_sha256_file(Path(runtime_cases_path)),
        "gold": q5_sha256_file(Path(gold_path)),
    }
    if q5_read_jsonl(target / "symbolic_rows.jsonl") != rows:
        raise ValueError("Q5 symbolic rows do not match deterministic recomputation")
    if q5_read_json(target / "symbolic_summary.json") != summary:
        raise ValueError("Q5 symbolic summary does not match deterministic recomputation")
    if (target / "symbolic_report.md").read_text(encoding="utf-8") != _render_report(summary):
        raise ValueError("Q5 symbolic report does not match deterministic recomputation")
    return summary


def _verify_frozen_symbolic_v1(
    *,
    tasks_path: Path | str,
    environment_path: Path | str,
    runtime_cases_path: Path | str,
    gold_path: Path | str,
    target: Path,
    hashes: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the committed 5-I symbolic v1 bytes without current-code replay."""

    if hashes.get("artifacts") != _FROZEN_SYMBOLIC_V1_ARTIFACTS:
        raise ValueError("Q5 symbolic v1 sidecar is not a frozen artifact")
    for name, expected_hash in _FROZEN_SYMBOLIC_V1_ARTIFACTS.items():
        if q5_sha256_file(target / name) != expected_hash:
            raise ValueError(f"Q5 symbolic v1 artifact hash mismatch: {name}")
    summary = q5_read_json(target / "symbolic_summary.json")
    expected_inputs = {
        "tasks": q5_sha256_file(Path(tasks_path)),
        "environment": q5_sha256_file(Path(environment_path)),
        "runtime_cases": q5_sha256_file(Path(runtime_cases_path)),
        "gold": q5_sha256_file(Path(gold_path)),
    }
    if (
        summary.get("schema_version") != "q5-strong-symbolic-summary-v1"
        or summary.get("input_sha256") != expected_inputs
    ):
        raise ValueError("Q5 symbolic v1 input provenance mismatch")
    return summary


def _clauses(text: str) -> list[str]:
    return [part.strip().lower() for part in re.split(r"[.;]", text) if part.strip()]


def q5_symbolic_policy_match(
    policy_text: str,
    *,
    status: str,
    observed_scope: str | None,
    requested_scope: str | None,
) -> str | None:
    """Return one generic disposition name, or None for unknown/ambiguous text."""

    parsed = [
        _dispositions(clause)
        for clause in _clauses(policy_text)
        if _clause_matches_state(
            clause,
            status=status,
            observed_scope=observed_scope,
            requested_scope=requested_scope,
        )
    ]
    if not parsed or any(len(dispositions) != 1 for dispositions in parsed):
        return None
    unique = {dispositions[0] for dispositions in parsed}
    return next(iter(unique)) if len(unique) == 1 else None


def _requested_scope(query: str) -> str | None:
    lowered = query.lower()
    return next(
        (
            scope
            for scope in ("production", "staging", "sandbox", "development")
            if re.search(rf"\b{scope}\b", lowered)
        ),
        None,
    )


def _clause_matches_state(
    clause: str,
    *,
    status: str,
    observed_scope: str | None,
    requested_scope: str | None,
) -> bool:
    scope_known = observed_scope is not None and requested_scope is not None
    if "matching" in clause:
        return status == "active" and (not scope_known or observed_scope == requested_scope)
    if "scope mismatch" in clause or "another deployment scope" in clause:
        return status == "active" and scope_known and observed_scope != requested_scope
    status_terms = {
        "degraded": ("degraded", "degradation"),
        "outage": ("outage",),
        "planned": ("planned",),
        "completed": ("completed",),
        "active": ("active",),
    }.get(status, (status,))
    return any(term and term in clause for term in status_terms)


def _dispositions(clause: str) -> list[str]:
    return sorted(
        name
        for name, phrases in _DISPOSITION_LEXICON.items()
        if any(phrase in clause for phrase in phrases)
    )


def _gold_tag(gold: Q5Gold, prefix: str) -> str | None:
    matches = [tag for tag in gold.gold_reason_tags if tag.startswith(prefix)]
    if gold.stratum.value == "semantic" and len(matches) != 1:
        raise ValueError(f"Q5 symbolic grading requires one {prefix} tag")
    if gold.stratum.value != "semantic" and matches:
        raise ValueError("Q5 non-semantic symbolic row carries a pair tag")
    return matches[0] if matches else None


def _config_sha256() -> str:
    payload = {
        "disposition_lexicon": dict(_DISPOSITION_LEXICON),
        "success_statuses": sorted(_SUCCESS_STATUSES),
        "clause_split": "period_or_semicolon",
        "unknown_or_ambiguous": "safe_escalation",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_inventory() -> dict[str, str]:
    project_root = Path(__file__).resolve().parents[2]
    inventory = {
        relative: q5_sha256_file(project_root / relative)
        for relative in _SYMBOLIC_SOURCE_DEPENDENCIES
    }
    if set(inventory) != set(_SYMBOLIC_SOURCE_DEPENDENCIES):  # pragma: no cover
        raise ValueError("Q5 symbolic source inventory is incomplete")
    return dict(sorted(inventory.items()))


def _render_report(summary: Mapping[str, Any]) -> str:
    return (
        "# Q5 Strong Symbolic Control\n\n"
        "- Control type: `frozen closed-vocabulary parser`\n"
        "- Claim scope: this control shows that the v4 benchmark does not support "
        "an LLM-necessity claim; it does not establish general natural-language "
        "rule-solving ability.\n"
        f"- Entire source file SHA-256: `{summary['source_file_sha256']}`\n"
        f"- Execution dependency inventory entries: "
        f"`{len(summary['source_dependency_sha256'])}`\n"
        f"- Semantic success: `{summary['semantic_success']:.6f}`\n"
        f"- Within-policy pair success: `{summary['within_policy_pair_success']:.6f}`\n"
        f"- Cross-policy pair success: `{summary['cross_policy_pair_success']:.6f}`\n"
        f"- LLM calls: `{summary['llm_calls']}`\n"
        f"- Total tokens: `{summary['total_tokens']}`\n"
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
