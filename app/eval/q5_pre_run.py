"""Static pre-run validation for formally authored Q5 datasets.

The checker deliberately runs before any policy model.  It replays the
deterministic retrieval gates, validates task/runtime/gold closure, and proves
that ACL-blocked text cannot reach the initial Q5 context or prompt.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.eval.q5_dataset import (
    build_q5_dataset_manifest,
    load_q5_environment,
    load_q5_gold,
    load_q5_tasks,
    validate_q5_dataset,
)
from app.eval.q5_runner import load_q5_runtime_cases
from app.govern.conditions import (
    ActorContext,
    GovernanceAction,
    detect_conditions,
)
from app.govern.q5_context import (
    Q5_AUTHORIZED_TEXT_CHAR_LIMIT,
    Q5_EXCERPT_CHAR_LIMIT,
    build_q5_context_trace,
    build_q5_decision_context,
    build_q5_prompt,
)
from app.govern.validator import legal_actions_for_report
from app.guards.acl_gate import apply_acl_gate
from app.guards.conflict_detector import detect_minimal_conflict
from app.guards.document_state_gate import apply_document_state_gate
from app.guards.evidence_gate import apply_evidence_gate
from app.schemas.q5_task import Q5_GOLD_ONLY_FIELDS, RequestedCapability

Q5_DEV_EXPECTED_STRATA: Mapping[str, int] = {
    "deterministic": 12,
    "semantic": 12,
    "adversarial": 12,
}
Q5_DEV_EXPECTED_SEMANTIC_FAMILIES: Mapping[str, int] = {
    "semantic_family_policy_exception": 4,
    "semantic_family_change_state": 4,
    "semantic_family_incident_impact": 4,
}
_CAPABILITY_REQUESTED_ACTION: Mapping[RequestedCapability, GovernanceAction | None] = {
    RequestedCapability.document_maintenance: GovernanceAction.flag_stale,
    RequestedCapability.remediation_management: GovernanceAction.open_remediation_ticket,
    RequestedCapability.incident_response: GovernanceAction.send_alert,
    RequestedCapability.investigate: None,
}
_VALID_REF_PREFIXES = ("resource:", "policy:", "change:")
_VALID_ASSERTION_PATHS = {"records", "pending_queue"}
_VALID_ASSERTION_OPERATORS = {
    "equals",
    "eq",
    "not_equals",
    "ne",
    "contains",
    "not_contains",
    "unchanged",
    "changed",
    "exists",
    "absent",
    "length_equals",
    "count_equals",
}


class Q5PreRunReport(BaseModel):
    """Machine-readable evidence that a formal dataset is safe to execute."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["q5-pre-run-v1"] = "q5-pre-run-v1"
    dataset_partition: Literal["dev", "test"]
    valid: bool
    task_count: int = Field(ge=0)
    environment_count: int = Field(ge=0)
    runtime_case_count: int = Field(ge=0)
    gold_count: int = Field(ge=0)
    stratum_counts: dict[str, int] = Field(default_factory=dict)
    semantic_family_counts: dict[str, int] = Field(default_factory=dict)
    namespace_counts: dict[str, int] = Field(default_factory=dict)
    source_origin_counts: dict[str, int] = Field(default_factory=dict)
    corpus_document_count: int = Field(ge=0, default=0)
    authorized_chunk_count: int = Field(ge=0, default=0)
    blocked_chunk_count: int = Field(ge=0, default=0)
    checked_prompt_count: int = Field(ge=0, default=0)
    sha256: dict[str, str] = Field(default_factory=dict)
    checks: dict[str, bool] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def check_q5_pre_run(
    root: Path | str,
    *,
    dataset_partition: Literal["dev", "test"] = "dev",
    verify_receipt: bool = True,
) -> Q5PreRunReport:
    """Validate a formal Q5 dataset without executing a policy model."""

    base = Path(root)
    paths = {
        "tasks": base / "tasks.jsonl",
        "environment": base / "environment.jsonl",
        "runtime_cases": base / "runtime_cases.jsonl",
        "gold": base / "gold.jsonl",
        "corpus": base / "corpus",
        "manifest": base / "manifest.json",
    }
    errors: list[str] = []
    warnings: list[str] = []
    checks = {
        "dataset_contract": True,
        "formal_partition_shape": True,
        "runtime_case_closure": True,
        "runtime_gate_replay": True,
        "context_prompt_leakage": True,
        "corpus_provenance": True,
        "manifest_integrity": True,
        "pre_run_receipt": True,
    }

    def fail(check: str, message: str) -> None:
        checks[check] = False
        errors.append(f"{check}: {message}")

    try:
        tasks = load_q5_tasks(paths["tasks"])
        environment = load_q5_environment(paths["environment"])
        runtime_cases = load_q5_runtime_cases(paths["runtime_cases"])
        gold = load_q5_gold(paths["gold"])
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        fail("dataset_contract", str(exc))
        return _empty_report(
            dataset_partition=dataset_partition,
            checks=checks,
            errors=errors,
            warnings=warnings,
        )

    dataset_report = validate_q5_dataset(tasks, environment, gold)
    for message in dataset_report.errors:
        fail("dataset_contract", message)
    warnings.extend(dataset_report.warnings)

    task_ids = {task.case_id for task in tasks}
    if set(runtime_cases) != task_ids:
        fail(
            "runtime_case_closure",
            "runtime/task case mismatch: "
            f"missing={sorted(task_ids - set(runtime_cases))}, "
            f"extra={sorted(set(runtime_cases) - task_ids)}",
        )

    stratum_counts = Counter(row.stratum.value for row in gold.values())
    namespace_counts = Counter(task.corpus_namespace for task in tasks)
    semantic_family_counts = Counter(
        tag
        for row in gold.values()
        if row.stratum.value == "semantic"
        for tag in row.gold_reason_tags
        if tag.startswith("semantic_family_")
    )
    if dataset_partition == "dev":
        if dict(stratum_counts) != dict(Q5_DEV_EXPECTED_STRATA):
            fail(
                "formal_partition_shape",
                f"q5_dev strata must be {dict(Q5_DEV_EXPECTED_STRATA)}, "
                f"got {dict(stratum_counts)}",
            )
        if dict(semantic_family_counts) != dict(
            Q5_DEV_EXPECTED_SEMANTIC_FAMILIES
        ):
            fail(
                "formal_partition_shape",
                "q5_dev semantic families must be "
                f"{dict(Q5_DEV_EXPECTED_SEMANTIC_FAMILIES)}, "
                f"got {dict(semantic_family_counts)}",
            )
    expected_namespace_prefix = f"q5_{dataset_partition}"
    for task in tasks:
        if not task.corpus_namespace.lower().replace("-", "_").startswith(
            expected_namespace_prefix
        ):
            fail(
                "formal_partition_shape",
                f"{task.case_id} uses non-{dataset_partition} namespace "
                f"{task.corpus_namespace}",
            )
        case_gold = gold.get(task.case_id)
        if case_gold is None:
            continue
        normalized_namespace = task.corpus_namespace.lower().replace("-", "_")
        if case_gold.stratum.value == "adversarial":
            if not normalized_namespace.startswith(f"q5_{dataset_partition}_adversarial"):
                fail(
                    "formal_partition_shape",
                    f"{task.case_id} adversarial text is not isolated in its namespace",
                )
        elif "adversarial" in normalized_namespace:
            fail(
                "formal_partition_shape",
                f"{task.case_id} non-adversarial case uses adversarial namespace",
            )

    referenced_environments = [task.environment_ref for task in tasks]
    if len(referenced_environments) != len(set(referenced_environments)):
        fail(
            "formal_partition_shape",
            "formal q5 cases must use isolated environment_ref values",
        )
    if set(referenced_environments) != set(environment):
        fail(
            "formal_partition_shape",
            "formal q5 environments must have exact one-case closure",
        )

    corpus_text, corpus_document_ids, provenance = _load_corpus(paths["corpus"])
    if provenance is None:
        fail("corpus_provenance", "corpus/provenance.json is missing or invalid")
    else:
        if provenance.get("document_content_origin") != "generated_synthetic":
            fail(
                "corpus_provenance",
                "q5_dev corpus origin disclosure must be generated_synthetic",
            )
        if provenance.get("environment_state_origin") != "deterministic_synthetic":
            fail(
                "corpus_provenance",
                "q5_dev environment origin disclosure must be deterministic_synthetic",
            )
        warnings.append(
            "q5_dev corpus and tool state are disclosed synthetic diagnostic data; "
            "they are not headline evidence"
        )

    source_origins: Counter[str] = Counter()
    authorized_chunk_count = 0
    blocked_chunk_count = 0
    checked_prompt_count = 0
    for task in tasks:
        runtime_case = runtime_cases.get(task.case_id)
        case_gold = gold.get(task.case_id)
        if runtime_case is None or case_gold is None:
            continue
        if runtime_case.pass_result.query != task.query:
            fail("runtime_case_closure", f"{task.case_id} query mismatch")
        if runtime_case.report.authorized_actor is not case_gold.authorized:
            fail(
                "runtime_case_closure",
                f"{task.case_id} authorized label disagrees with replayable actor role",
            )
        for value in task.resource_refs:
            if not value.startswith(_VALID_REF_PREFIXES):
                fail(
                    "dataset_contract",
                    f"{task.case_id} has invalid resource reference {value}",
                )
        required = set(case_gold.required_observations)
        available = {tool.value for tool in task.available_tools}
        if not required.issubset(available):
            fail(
                "formal_partition_shape",
                f"{task.case_id} requires tools absent from runtime allowlist",
            )
        if len(required) > task.max_observation_steps:
            fail(
                "formal_partition_shape",
                f"{task.case_id} observation requirement exceeds task budget",
            )
        _validate_gold_assertions(case_gold.final_state_assertions, task.case_id, fail)

        pass_result = runtime_case.pass_result
        for item in pass_result.retrieved_chunks:
            source_origins[item.chunk.source_origin.value] += 1
            if item.chunk.text not in corpus_text:
                fail(
                    "corpus_provenance",
                    f"{task.case_id} chunk {item.chunk.chunk_id} text is absent from corpus",
                )
            if item.chunk.doc_id not in corpus_document_ids:
                fail(
                    "corpus_provenance",
                    f"{task.case_id} doc {item.chunk.doc_id} is absent from corpus headings",
                )
        _validate_source_refs(
            case_id=task.case_id,
            refs=case_gold.source_refs,
            corpus_document_ids=corpus_document_ids,
            fail=fail,
        )

        replay_state = apply_document_state_gate(pass_result.retrieved_chunks)
        replay_acl = apply_acl_gate(
            replay_state.surviving_chunks,
            task.actor.role,
            task.actor.department,
            task.actor.clearance,
        )
        replay_conflict = detect_minimal_conflict(replay_acl.surviving_chunks)
        replay_evidence = apply_evidence_gate(
            task.query,
            replay_acl.surviving_chunks,
            min_score=0.5,
        )
        if replay_state.model_dump(mode="json") != (
            pass_result.state_decision.model_dump(mode="json")
        ):
            fail("runtime_gate_replay", f"{task.case_id} state gate mismatch")
        if replay_acl.model_dump(mode="json") != (
            pass_result.acl_decision.model_dump(mode="json")
        ):
            fail("runtime_gate_replay", f"{task.case_id} ACL gate mismatch")
        if replay_conflict.model_dump(mode="json") != (
            pass_result.conflict_decision.model_dump(mode="json")
        ):
            fail("runtime_gate_replay", f"{task.case_id} conflict gate mismatch")
        if replay_evidence.model_dump(mode="json") != (
            pass_result.evidence_decision.model_dump(mode="json")
        ):
            fail("runtime_gate_replay", f"{task.case_id} evidence gate mismatch")

        replay_pass = pass_result.model_copy(
            update={
                "state_decision": replay_state,
                "acl_decision": replay_acl,
                "conflict_decision": replay_conflict,
                "evidence_decision": replay_evidence,
            }
        )
        replay_report = detect_conditions(
            replay_pass,
            ActorContext(
                role=task.actor.role,
                clearance=task.actor.clearance,
                department=task.actor.department,
                requested_action=_CAPABILITY_REQUESTED_ACTION[
                    task.requested_capability
                ],
            ),
        )
        if replay_report.model_dump(mode="json") != runtime_case.report.model_dump(
            mode="json"
        ):
            fail("runtime_gate_replay", f"{task.case_id} condition report mismatch")

        try:
            context = build_q5_decision_context(
                replay_pass,
                actor_claims=task.actor,
                requested_capability=task.requested_capability,
                resource_refs=task.resource_refs,
                available_tools=task.available_tools,
                conditions=replay_report.conditions,
                evidence_decision=replay_report.evidence_decision,
                condition_legal_actions=legal_actions_for_report(replay_report),
                remaining_observation_budget=task.max_observation_steps,
                remaining_terminal_budget=1,
            )
            prompt = build_q5_prompt(context)
            trace = json.dumps(
                build_q5_context_trace(context, context_version=1),
                ensure_ascii=False,
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            fail(
                "context_prompt_leakage",
                f"{task.case_id} context construction failed: {exc}",
            )
            continue
        checked_prompt_count += 1
        authorized_chunk_count += len(context.authorized_evidence)
        blocked_chunk_count += len(context.blocked_evidence_metadata)
        if any(
            len(item.text_excerpt) > Q5_EXCERPT_CHAR_LIMIT
            for item in context.authorized_evidence
        ):
            fail(
                "context_prompt_leakage",
                f"{task.case_id} authorized excerpt exceeds limit",
            )
        if sum(len(item.text_excerpt) for item in context.authorized_evidence) > (
            Q5_AUTHORIZED_TEXT_CHAR_LIMIT
        ):
            fail(
                "context_prompt_leakage",
                f"{task.case_id} authorized context exceeds total text limit",
            )
        legal = {action.value for action in context.legal_terminal_actions}
        if not set(case_gold.allowed_terminal_actions).issubset(legal):
            fail(
                "runtime_case_closure",
                f"{task.case_id} gold allows an action outside runtime authorization",
            )
        serialized_context = context.model_dump_json()
        authorized_values = {
            value
            for item in replay_acl.surviving_chunks
            for value in [item.chunk.text, *item.chunk.section_path]
        }
        for blocked in replay_acl.blocked_chunks:
            markers = [blocked.chunk.text, *blocked.chunk.section_path]
            for marker in markers:
                if len(marker.strip()) < 12 or marker in authorized_values:
                    continue
                if marker in prompt or marker in trace or marker in serialized_context:
                    fail(
                        "context_prompt_leakage",
                        f"{task.case_id} blocked marker reached context/prompt/trace",
                    )

    runtime_payload = {
        case_id: runtime_cases[case_id].model_dump(mode="json")
        for case_id in sorted(runtime_cases)
    }
    forbidden = _find_gold_fields(runtime_payload)
    if forbidden:
        fail(
            "context_prompt_leakage",
            "runtime ledger contains grader-only fields: " + ", ".join(forbidden),
        )

    expected_manifest = build_q5_dataset_manifest(
        tasks_path=paths["tasks"],
        environment_path=paths["environment"],
        gold_path=paths["gold"],
        corpus_path=paths["corpus"],
    )
    try:
        persisted_manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        fail("manifest_integrity", str(exc))
        persisted_manifest = None
    if persisted_manifest is not None and not _manifest_matches(
        persisted_manifest,
        expected_manifest,
    ):
        fail("manifest_integrity", "manifest hashes or paths do not match dataset")

    hashes = {
        **expected_manifest["sha256"],
        "runtime_cases": _sha256_file(paths["runtime_cases"]),
        "manifest": _sha256_file(paths["manifest"]),
    }
    report = Q5PreRunReport(
        dataset_partition=dataset_partition,
        valid=not errors,
        task_count=len(tasks),
        environment_count=len(environment),
        runtime_case_count=len(runtime_cases),
        gold_count=len(gold),
        stratum_counts=dict(sorted(stratum_counts.items())),
        semantic_family_counts=dict(sorted(semantic_family_counts.items())),
        namespace_counts=dict(sorted(namespace_counts.items())),
        source_origin_counts=dict(sorted(source_origins.items())),
        corpus_document_count=len(corpus_document_ids),
        authorized_chunk_count=authorized_chunk_count,
        blocked_chunk_count=blocked_chunk_count,
        checked_prompt_count=checked_prompt_count,
        sha256=hashes,
        checks=checks,
        errors=errors,
        warnings=list(dict.fromkeys(warnings)),
    )
    if not verify_receipt:
        return report
    receipt_path = base / "pre_run.json"
    try:
        persisted_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        persisted_receipt = None
        receipt_error = str(exc)
    else:
        receipt_error = "pre_run.json does not match the current dataset"
    if persisted_receipt == report.model_dump(mode="json"):
        return report
    updated_checks = dict(report.checks)
    updated_checks["pre_run_receipt"] = False
    return report.model_copy(
        update={
            "valid": False,
            "checks": updated_checks,
            "errors": [*report.errors, f"pre_run_receipt: {receipt_error}"],
        }
    )


def _empty_report(
    *,
    dataset_partition: Literal["dev", "test"],
    checks: dict[str, bool],
    errors: list[str],
    warnings: list[str],
) -> Q5PreRunReport:
    return Q5PreRunReport(
        dataset_partition=dataset_partition,
        valid=False,
        task_count=0,
        environment_count=0,
        runtime_case_count=0,
        gold_count=0,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )


def _load_corpus(corpus_path: Path) -> tuple[str, set[str], dict[str, Any] | None]:
    if not corpus_path.is_dir():
        return "", set(), None
    markdown_files = sorted(corpus_path.rglob("*.md"))
    corpus_text = "\n".join(path.read_text(encoding="utf-8") for path in markdown_files)
    document_ids = {
        line.removeprefix("## ").strip()
        for line in corpus_text.splitlines()
        if line.startswith("## ")
    }
    provenance_path = corpus_path / "provenance.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        provenance = None
    return corpus_text, document_ids, provenance if isinstance(provenance, dict) else None


def _validate_source_refs(
    *,
    case_id: str,
    refs: Sequence[str],
    corpus_document_ids: set[str],
    fail,
) -> None:
    if not refs:
        fail("corpus_provenance", f"{case_id} has no source_refs")
        return
    for ref in refs:
        if ref.startswith("corpus:"):
            doc_id = ref.removeprefix("corpus:")
            if doc_id not in corpus_document_ids:
                fail(
                    "corpus_provenance",
                    f"{case_id} source_ref points to unknown doc {doc_id}",
                )
        elif not ref.startswith("scenario:"):
            fail("corpus_provenance", f"{case_id} has unsupported source_ref {ref}")


def _validate_gold_assertions(
    assertions: Sequence[dict[str, Any]],
    case_id: str,
    fail,
) -> None:
    for assertion in assertions:
        path = assertion.get("path")
        operator = assertion.get("operator")
        if path not in _VALID_ASSERTION_PATHS:
            fail(
                "formal_partition_shape",
                f"{case_id} assertion reads non-outcome path {path}",
            )
        if operator not in _VALID_ASSERTION_OPERATORS:
            fail(
                "formal_partition_shape",
                f"{case_id} assertion uses unsupported operator {operator}",
            )


def _manifest_matches(persisted: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(persisted, Mapping):
        return False
    if persisted.get("schema_version") != expected.get("schema_version"):
        return False
    if persisted.get("sha256") != expected.get("sha256"):
        return False
    paths = persisted.get("paths")
    expected_paths = expected.get("paths")
    if not isinstance(paths, Mapping) or not isinstance(expected_paths, Mapping):
        return False
    if set(paths) != set(expected_paths):
        return False
    return all(
        Path(str(paths[name])).name == Path(str(expected_paths[name])).name
        for name in paths
    )


def _find_gold_fields(payload: Any) -> list[str]:
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized = str(key).strip().lower()
                if normalized in Q5_GOLD_ONLY_FIELDS or normalized.startswith("gold_"):
                    found.add(normalized)
                visit(nested)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for nested in value:
                visit(nested)

    visit(payload)
    return sorted(found)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
