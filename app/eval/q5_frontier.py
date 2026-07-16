"""Isolated, hash-closed Q5 v5 neuro-symbolic capability frontier.

This module authors and verifies a development-only frontier. It does not load
the legacy Q5 dataset, does not call a model, and keeps sealed Policy IR and
topology rows physically separate from runtime-visible payloads.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.schemas.q5_frontier import (
    CanonicalPolicyIR,
    FrontierAmbiguityConflict,
    FrontierAmbiguityKind,
    FrontierConditionExpression,
    FrontierDisposition,
    FrontierEnvironmentState,
    FrontierEvidenceRequirements,
    FrontierExceptionClause,
    FrontierGold,
    FrontierParserResult,
    FrontierPolicyScope,
    FrontierPrecedence,
    FrontierPredicate,
    FrontierPredicateField,
    FrontierPredicateOperator,
    FrontierResourceType,
    FrontierRouteDecision,
    FrontierRouteFacts,
    FrontierRuntimePayload,
    FrontierTemporalState,
    FrontierTerminalSafetyConstraints,
    FrontierTopologyRow,
    compact_policy_ir_schema,
)

FRONTIER_SCHEMA_VERSION = "q5-frontier-v5-dataset-manifest-v1"
FRONTIER_HASHES_SCHEMA = "q5-frontier-v5-hashes-v1"
FRONTIER_CASE_COUNT = 48
FRONTIER_ARTIFACT_FILES = frozenset(
    {
        "policy_ir.jsonl",
        "environment.jsonl",
        "runtime_cases.jsonl",
        "topology.jsonl",
        "gold.jsonl",
        "baseline_rows.jsonl",
        "policy_ir_manifest.json",
        "frontier_dataset_manifest.json",
        "renderer_manifest.json",
        "baseline_manifest.json",
        "claim_preregistration.json",
        "leakage_report.json",
        "frontier_hashes.json",
    }
)
_CAPABILITY_COUNTS = {
    "symbolic_complete": 16,
    "semantic_open": 20,
    "ambiguous_or_unsafe": 12,
}
_FAMILY_CLASS_COUNTS: Mapping[FrontierResourceType, Mapping[str, int]] = {
    FrontierResourceType.incident: {
        "symbolic_complete": 4,
        "semantic_open": 6,
        "ambiguous_or_unsafe": 2,
    },
    FrontierResourceType.change: {
        "symbolic_complete": 4,
        "semantic_open": 6,
        "ambiguous_or_unsafe": 2,
    },
    FrontierResourceType.access: {
        "symbolic_complete": 4,
        "semantic_open": 4,
        "ambiguous_or_unsafe": 4,
    },
    FrontierResourceType.retention: {
        "symbolic_complete": 4,
        "semantic_open": 4,
        "ambiguous_or_unsafe": 4,
    },
}
_FAMILY_FACTS: Mapping[FrontierResourceType, tuple[FrontierPredicateField, str, str]] = {
    FrontierResourceType.incident: (
        FrontierPredicateField.status,
        "outage",
        "nominal",
    ),
    FrontierResourceType.change: (
        FrontierPredicateField.temporal_state,
        "planned",
        "completed",
    ),
    FrontierResourceType.access: (
        FrontierPredicateField.scope,
        "restricted",
        "public",
    ),
    FrontierResourceType.retention: (
        FrontierPredicateField.status,
        "expired",
        "current",
    ),
}
_OBSERVATION_TYPE: Mapping[FrontierResourceType, str] = {
    FrontierResourceType.incident: "inspect_incident_state",
    FrontierResourceType.change: "inspect_change_state",
    FrontierResourceType.access: "inspect_access_scope",
    FrontierResourceType.retention: "inspect_retention_state",
}
_TRUE_DISPOSITION: Mapping[FrontierResourceType, FrontierDisposition] = {
    FrontierResourceType.incident: FrontierDisposition.remediate,
    FrontierResourceType.change: FrontierDisposition.notify,
    FrontierResourceType.access: FrontierDisposition.notify,
    FrontierResourceType.retention: FrontierDisposition.mark_stale,
}
_ALL_DISPOSITIONS = list(FrontierDisposition)
_SOURCE_FILES = (
    "app/eval/q5_frontier.py",
    "app/schemas/q5_frontier.py",
)
_RUNTIME_FORBIDDEN_KEYS = frozenset(
    {
        "ir",
        "policy_ir",
        "gold",
        "stratum",
        "capability_class",
        "pair_id",
        "pair_kind",
        "policy_family",
        "family",
        "renderer_id",
        "expected_action",
        "expected_disposition",
    }
)


def compile_policy_ir(
    policy_ir: CanonicalPolicyIR,
    state: FrontierEnvironmentState,
) -> FrontierGold:
    """Compile sealed IR and environment state without identity/text lookup."""

    safety = policy_ir.terminal_safety
    authorized = state.evidence_authorized
    evidence_ok = not safety.require_authorized_evidence or authorized
    observation_ok = (
        not safety.require_successful_observation or state.observation_successful
    )
    if policy_ir.ambiguity.kind != FrontierAmbiguityKind.none:
        disposition = FrontierDisposition.human_review
    elif not evidence_ok or not observation_ok:
        disposition = FrontierDisposition.human_review
    else:
        exception_matches = [
            exception
            for exception in policy_ir.exceptions
            if _evaluate_predicate(exception.predicate, state)
        ]
        if exception_matches and policy_ir.precedence in {
            FrontierPrecedence.exception_overrides,
            FrontierPrecedence.deny_overrides,
        }:
            unique = {exception.disposition for exception in exception_matches}
            disposition = (
                next(iter(unique))
                if len(unique) == 1
                else FrontierDisposition.human_review
            )
        else:
            disposition = (
                policy_ir.true_disposition
                if _evaluate_condition(policy_ir.condition, state)
                else policy_ir.false_disposition
            )
    if disposition not in safety.allowed_dispositions:
        disposition = FrontierDisposition.human_review
    return FrontierGold(
        runtime_ref=state.runtime_ref,
        disposition=disposition,
        authorized=authorized,
        evidence_chunk_id=state.authorized_evidence_chunk_id,
        observation_request_id=state.observation_request_id,
    )


def structured_grammar_parser(policy_text: str) -> FrontierParserResult:
    """Parse the explicit v5 grammar or abstain on every unsupported construct."""

    if not policy_text.startswith("Q5POLICYv5;"):
        if "CONFLICT[" in policy_text:
            return FrontierParserResult(
                status="ambiguous", reason="conflicting_clauses"
            )
        return FrontierParserResult(status="abstain", reason="incomplete_resolvable")
    upper = policy_text.upper()
    if re.search(r"\b(NOT|UNLESS|EXCEPT WHEN)\b", upper):
        return FrontierParserResult(status="abstain", reason="unsupported_construct")
    clauses: dict[str, str] = {}
    for raw_clause in policy_text.split(";")[1:]:
        clause = raw_clause.strip()
        if not clause:
            continue
        if clause.startswith("COMMENT "):
            continue
        key, separator, value = clause.partition(" ")
        if not separator or key not in {
            "RESOURCE",
            "SCOPES",
            "TEMPORAL",
            "WHEN",
            "TRUE",
            "FALSE",
            "EXCEPTION",
            "PRECEDENCE",
            "EVIDENCE",
            "SAFETY",
        }:
            return FrontierParserResult(
                status="abstain", reason="unsupported_construct"
            )
        if key in clauses:
            return FrontierParserResult(
                status="ambiguous", reason="conflicting_clauses"
            )
        clauses[key] = value.strip()
    required = {
        "RESOURCE",
        "SCOPES",
        "TEMPORAL",
        "WHEN",
        "TRUE",
        "FALSE",
        "EXCEPTION",
        "PRECEDENCE",
        "EVIDENCE",
        "SAFETY",
    }
    if set(clauses) != required:
        return FrontierParserResult(status="abstain", reason="unsupported_construct")
    try:
        predicates = [_parse_predicate(item) for item in clauses["WHEN"].split(" & ")]
        exception_text, arrow, exception_disposition = clauses["EXCEPTION"].partition(
            " -> "
        )
        if not arrow:
            raise ValueError("exception arrow is missing")
        policy_ir = CanonicalPolicyIR(
            scope=FrontierPolicyScope(
                resource_type=FrontierResourceType(clauses["RESOURCE"]),
                allowed_scopes=clauses["SCOPES"].split(","),
            ),
            condition=FrontierConditionExpression(all_of=predicates),
            temporal_state=FrontierTemporalState(clauses["TEMPORAL"]),
            exceptions=[
                FrontierExceptionClause(
                    predicate=_parse_predicate(exception_text),
                    disposition=FrontierDisposition(exception_disposition),
                )
            ],
            precedence=FrontierPrecedence(clauses["PRECEDENCE"]),
            evidence_requirements=FrontierEvidenceRequirements(
                observation_type=clauses["EVIDENCE"]
            ),
            true_disposition=FrontierDisposition(clauses["TRUE"]),
            false_disposition=FrontierDisposition(clauses["FALSE"]),
            ambiguity=FrontierAmbiguityConflict(),
            terminal_safety=FrontierTerminalSafetyConstraints(
                allowed_dispositions=[
                    FrontierDisposition(item) for item in clauses["SAFETY"].split(",")
                ]
            ),
        )
    except (TypeError, ValueError):
        return FrontierParserResult(status="abstain", reason="unsupported_construct")
    return FrontierParserResult(
        status="complete", reason="canonical_complete", parsed_ir=policy_ir
    )


def closed_vocabulary_parser(policy_text: str) -> FrontierParserResult:
    """Frozen non-LLM baseline; identical core prevents baseline/control drift."""

    return structured_grammar_parser(policy_text)


def validate_semantic_policy_ir(payload: Mapping[str, Any]) -> FrontierParserResult:
    """Validate a future LLM semantic parse through the canonical Pydantic IR.

    This function performs no model call. It is the only permitted handoff from
    the LLM-semantic-parser route back into deterministic compilation.
    """

    try:
        policy_ir = CanonicalPolicyIR.model_validate(payload)
    except (TypeError, ValueError):
        return FrontierParserResult(status="abstain", reason="unsupported_construct")
    if policy_ir.ambiguity.kind != FrontierAmbiguityKind.none:
        return FrontierParserResult(status="ambiguous", reason="conflicting_clauses")
    return FrontierParserResult(
        status="complete", reason="semantic_typed_complete", parsed_ir=policy_ir
    )


def route_frontier_policy(facts: FrontierRouteFacts) -> FrontierRouteDecision:
    """Route solely from parser/runtime safety facts, never grader identity."""

    legal = set(facts.legal_dispositions)
    if (
        not facts.evidence_authorized
        or not facts.observation_successful
        or facts.ambiguity_count > 0
        or facts.parser_status in {"ambiguous", "unsafe"}
    ):
        return FrontierRouteDecision(
            route="human_escalation",
            llm_allowed=False,
            terminal_disposition=FrontierDisposition.human_review,
        )
    if facts.parser_status == "complete":
        return FrontierRouteDecision(
            route="deterministic_parser_compiler", llm_allowed=False
        )
    if facts.parser_status == "abstain" and facts.parser_reason == (
        "incomplete_resolvable"
    ):
        return FrontierRouteDecision(route="llm_semantic_parser", llm_allowed=True)
    terminal = (
        FrontierDisposition.human_review
        if FrontierDisposition.human_review in legal
        else None
    )
    return FrontierRouteDecision(
        route="human_escalation", llm_allowed=False, terminal_disposition=terminal
    )


def build_frontier_artifacts() -> dict[str, bytes]:
    """Mechanically derive the complete v5 dev namespace."""

    authored = _author_frontier_rows()
    policy_rows = authored["policy_ir"]
    environment_rows = authored["environment"]
    runtime_rows = authored["runtime"]
    topology_rows = authored["topology"]
    gold_rows = authored["gold"]
    baseline_rows = _evaluate_baselines(authored)
    raw: dict[str, bytes] = {
        "policy_ir.jsonl": _jsonl_bytes(policy_rows),
        "environment.jsonl": _jsonl_bytes(environment_rows),
        "runtime_cases.jsonl": _jsonl_bytes(runtime_rows),
        "topology.jsonl": _jsonl_bytes(topology_rows),
        "gold.jsonl": _jsonl_bytes(gold_rows),
        "baseline_rows.jsonl": _jsonl_bytes(baseline_rows),
    }
    source_inventory = _source_inventory()
    ir_schema = compact_policy_ir_schema()
    ir_hash = _hash_payload(ir_schema)
    pair_ids: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in topology_rows:
        pair_ids[row["pair_id"]].append(row)
    pair_errors = [key for key, rows in pair_ids.items() if len(rows) != 2]
    if pair_errors:
        raise ValueError(f"frontier pair topology is incomplete: {pair_errors}")
    pair_kinds = Counter(rows[0]["pair_kind"] for rows in pair_ids.values())
    pair_kinds_by_class: dict[str, set[str]] = defaultdict(set)
    pair_kinds_by_family: dict[str, set[str]] = defaultdict(set)
    for rows in pair_ids.values():
        pair_kinds_by_class[rows[0]["capability_class"]].add(rows[0]["pair_kind"])
        pair_kinds_by_family[rows[0]["policy_family"]].add(rows[0]["pair_kind"])
    required_pair_kinds = {
        "policy_fixed_state_changed",
        "state_fixed_policy_changed",
    }
    if any(kinds != required_pair_kinds for kinds in pair_kinds_by_class.values()):
        raise ValueError("each capability class must cover both counterfactual pair kinds")
    if any(kinds != required_pair_kinds for kinds in pair_kinds_by_family.values()):
        raise ValueError("each policy family must cover both counterfactual pair kinds")
    policy_manifest = {
        "schema_version": "q5-frontier-v5-policy-ir-manifest-v1",
        "protocol_namespace": "q5-frontier-v5",
        "pydantic_schema_sha256": ir_hash,
        "canonical_schema": ir_schema,
        "policy_ir_row_count": len(policy_rows),
        "policy_ir_sha256": _sha256(raw["policy_ir.jsonl"]),
        "gold_compiler": "typed_ir_plus_environment_only",
        "source_sha256": source_inventory,
    }
    dataset_manifest = {
        "schema_version": FRONTIER_SCHEMA_VERSION,
        "protocol_namespace": "q5-frontier-v5",
        "namespace": "data/q5_frontier/dev",
        "partition": "dev",
        "case_count": len(runtime_rows),
        "capability_class_counts": dict(
            sorted(Counter(row["capability_class"] for row in topology_rows).items())
        ),
        "policy_family_counts": dict(
            sorted(Counter(row["policy_family"] for row in topology_rows).items())
        ),
        "policy_family_count": len({row["policy_family"] for row in topology_rows}),
        "pair_count": len(pair_ids),
        "pair_kind_counts": dict(sorted(pair_kinds.items())),
        "pair_kinds_by_capability_class": {
            key: sorted(value) for key, value in sorted(pair_kinds_by_class.items())
        },
        "pair_kinds_by_policy_family": {
            key: sorted(value) for key, value in sorted(pair_kinds_by_family.items())
        },
        "distinct_case_primary_unit": True,
        "k_is_not_semantic_replication": True,
        "runtime_payload_excludes_sealed_authoring": True,
        "row_sha256": {
            name: _sha256(payload)
            for name, payload in sorted(raw.items())
            if name != "baseline_rows.jsonl"
        },
    }
    renderer_manifest = _renderer_manifest(runtime_rows, topology_rows)
    baseline_manifest = _baseline_manifest(baseline_rows, topology_rows, gold_rows)
    preregistration = _claim_preregistration()
    leakage_report = _leakage_report(runtime_rows, gold_rows, topology_rows)
    raw.update(
        {
            "policy_ir_manifest.json": _json_bytes(policy_manifest),
            "frontier_dataset_manifest.json": _json_bytes(dataset_manifest),
            "renderer_manifest.json": _json_bytes(renderer_manifest),
            "baseline_manifest.json": _json_bytes(baseline_manifest),
            "claim_preregistration.json": _json_bytes(preregistration),
            "leakage_report.json": _json_bytes(leakage_report),
        }
    )
    hashes = {
        "schema_version": FRONTIER_HASHES_SCHEMA,
        "artifacts": {name: _sha256(payload) for name, payload in sorted(raw.items())},
    }
    raw["frontier_hashes.json"] = _json_bytes(hashes)
    if set(raw) != FRONTIER_ARTIFACT_FILES:
        raise ValueError("frontier artifact closure mismatch during build")
    return raw


def write_frontier_artifacts(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists():
        if any(target.iterdir()):
            raise FileExistsError(f"frontier output directory is not empty: {target}")
    else:
        target.mkdir(parents=True)
    artifacts = build_frontier_artifacts()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["frontier_dataset_manifest.json"])


def verify_frontier_artifacts(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    actual = {path.name for path in target.iterdir() if path.is_file()}
    if actual != FRONTIER_ARTIFACT_FILES:
        raise ValueError(
            "frontier artifact closure mismatch: "
            f"missing={sorted(FRONTIER_ARTIFACT_FILES - actual)}, "
            f"extra={sorted(actual - FRONTIER_ARTIFACT_FILES)}"
        )
    expected = build_frontier_artifacts()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"frontier artifact does not match recomputation: {name}")
    return json.loads(expected["frontier_dataset_manifest.json"])


def _author_frontier_rows() -> dict[str, list[dict[str, Any]]]:
    policy_rows: list[dict[str, Any]] = []
    environment_rows: list[dict[str, Any]] = []
    runtime_rows: list[dict[str, Any]] = []
    topology_rows: list[dict[str, Any]] = []
    gold_rows: list[dict[str, Any]] = []
    ordinal = 0
    pair_ordinal = 0
    for family, class_counts in _FAMILY_CLASS_COUNTS.items():
        for capability_class, count in class_counts.items():
            for _local_pair in range(count // 2):
                pair_ordinal += 1
                pair_kind = (
                    "policy_fixed_state_changed"
                    if pair_ordinal % 2
                    else "state_fixed_policy_changed"
                )
                pair_id = f"frontier-pair-{pair_ordinal:02d}"
                for member in range(2):
                    ordinal += 1
                    runtime_ref = f"frontier-resource:r{ordinal:03d}"
                    ir, state = _author_case_meaning(
                        family=family,
                        capability_class=capability_class,
                        pair_kind=pair_kind,
                        member=member,
                        ordinal=ordinal,
                    )
                    renderer_id, policy_text = _render_policy(
                        ir, capability_class=capability_class, ordinal=ordinal
                    )
                    runtime = FrontierRuntimePayload(
                        runtime_ref=runtime_ref,
                        policy_text=policy_text,
                        query=(
                            "Apply the policy to the trusted observation and choose "
                            "one safe disposition."
                        ),
                        legal_dispositions=list(ir.terminal_safety.allowed_dispositions),
                        authorized_evidence_chunk_ids=[
                            state.authorized_evidence_chunk_id
                        ],
                        trusted_observation={
                            "status": state.status,
                            "scope": state.scope,
                            "temporal_state": state.temporal_state.value,
                            "exception_active": state.exception_active,
                            "observation_successful": state.observation_successful,
                            "observation_request_id": state.observation_request_id,
                        },
                    )
                    topology = FrontierTopologyRow(
                        runtime_ref=runtime_ref,
                        capability_class=capability_class,
                        policy_family=family,
                        pair_id=pair_id,
                        pair_kind=pair_kind,
                        renderer_id=renderer_id,
                    )
                    gold = compile_policy_ir(ir, state)
                    policy_rows.append(
                        {"runtime_ref": runtime_ref, "policy_ir": ir.model_dump(mode="json")}
                    )
                    environment_rows.append(state.model_dump(mode="json"))
                    runtime_rows.append(runtime.model_dump(mode="json"))
                    topology_rows.append(topology.model_dump(mode="json"))
                    gold_rows.append(gold.model_dump(mode="json"))
    if ordinal != FRONTIER_CASE_COUNT:
        raise ValueError(f"frontier authoring emitted {ordinal} cases")
    return {
        "policy_ir": policy_rows,
        "environment": environment_rows,
        "runtime": runtime_rows,
        "topology": topology_rows,
        "gold": gold_rows,
    }


def _author_case_meaning(
    *,
    family: FrontierResourceType,
    capability_class: str,
    pair_kind: str,
    member: int,
    ordinal: int,
) -> tuple[CanonicalPolicyIR, FrontierEnvironmentState]:
    field, true_value, false_value = _FAMILY_FACTS[family]
    state_value = true_value
    expected_value = true_value
    if pair_kind == "policy_fixed_state_changed":
        state_value = true_value if member == 0 else false_value
    else:
        expected_value = true_value if member == 0 else false_value
    ambiguity = FrontierAmbiguityConflict()
    authorized = True
    if capability_class == "ambiguous_or_unsafe":
        if ordinal % 2:
            ambiguity = FrontierAmbiguityConflict(
                kind=FrontierAmbiguityKind.conflicting_clauses,
                conflict_count=2,
            )
        else:
            authorized = False
    policy_ir = CanonicalPolicyIR(
        scope=FrontierPolicyScope(
            resource_type=family,
            allowed_scopes=["production", "staging", "restricted", "public"],
        ),
        condition=FrontierConditionExpression(
            all_of=[
                FrontierPredicate(
                    field=field,
                    operator=FrontierPredicateOperator.eq,
                    value=expected_value,
                )
            ]
        ),
        temporal_state=FrontierTemporalState.current,
        exceptions=[
            FrontierExceptionClause(
                predicate=FrontierPredicate(
                    field=FrontierPredicateField.exception_active,
                    operator=FrontierPredicateOperator.eq,
                    value=True,
                ),
                disposition=FrontierDisposition.human_review,
            )
        ],
        precedence=FrontierPrecedence.exception_overrides,
        evidence_requirements=FrontierEvidenceRequirements(
            observation_type=_OBSERVATION_TYPE[family]
        ),
        true_disposition=_TRUE_DISPOSITION[family],
        false_disposition=FrontierDisposition.no_action,
        ambiguity=ambiguity,
        terminal_safety=FrontierTerminalSafetyConstraints(
            allowed_dispositions=list(_ALL_DISPOSITIONS)
        ),
    )
    values: dict[str, Any] = {
        "status": "nominal",
        "scope": "production",
        "temporal_state": FrontierTemporalState.current,
    }
    if field == FrontierPredicateField.temporal_state:
        values["temporal_state"] = FrontierTemporalState(state_value)
    else:
        values[field.value] = state_value
    state = FrontierEnvironmentState(
        runtime_ref=f"frontier-resource:r{ordinal:03d}",
        status=values["status"],
        scope=values["scope"],
        temporal_state=values["temporal_state"],
        exception_active=False,
        evidence_authorized=authorized,
        authorized_evidence_chunk_id=f"chunk:c{ordinal:03d}",
        observation_successful=True,
        observation_request_id=f"observation:o{ordinal:03d}",
    )
    return policy_ir, state


def _render_policy(
    policy_ir: CanonicalPolicyIR,
    *,
    capability_class: str,
    ordinal: int,
) -> tuple[str, str]:
    if capability_class == "symbolic_complete":
        renderer_id = "frontier-dev-structured-grammar-v1"
        clauses = _structured_clauses(policy_ir)
        if ordinal % 2 == 0:
            clauses = list(reversed(clauses))
        clauses.append("COMMENT audit-neutral")
        return renderer_id, "Q5POLICYv5; " + "; ".join(clauses)
    if capability_class == "semantic_open":
        renderer_id = "frontier-dev-semantic-prose-v1"
        predicate = policy_ir.condition.all_of[0]
        return renderer_id, (
            f"For {policy_ir.scope.resource_type.value} governance, the authorized "
            f"observation should be interpreted in context. When {predicate.field.value} "
            f"matches {predicate.value}, use the {policy_ir.true_disposition.value} "
            f"disposition; otherwise use {policy_ir.false_disposition.value}. A confirmed "
            "exception takes precedence and requires human review."
        )
    renderer_id = "frontier-dev-ambiguity-probe-v1"
    if policy_ir.ambiguity.kind != FrontierAmbiguityKind.none:
        return renderer_id, (
            "CONFLICT[the policy both requires remediation and forbids deciding which "
            "disposition applies]; request clarification."
        )
    return renderer_id, (
        "Use the policy if applicable, but the evidence is not authorized for a "
        "terminal governance decision."
    )


def _structured_clauses(policy_ir: CanonicalPolicyIR) -> list[str]:
    predicates = " & ".join(_render_predicate(item) for item in policy_ir.condition.all_of)
    exception = policy_ir.exceptions[0]
    return [
        f"RESOURCE {policy_ir.scope.resource_type.value}",
        f"SCOPES {','.join(policy_ir.scope.allowed_scopes)}",
        f"TEMPORAL {policy_ir.temporal_state.value}",
        f"WHEN {predicates}",
        f"TRUE {policy_ir.true_disposition.value}",
        f"FALSE {policy_ir.false_disposition.value}",
        (
            f"EXCEPTION {_render_predicate(exception.predicate)} -> "
            f"{exception.disposition.value}"
        ),
        f"PRECEDENCE {policy_ir.precedence.value}",
        f"EVIDENCE {policy_ir.evidence_requirements.observation_type}",
        (
            "SAFETY "
            + ",".join(item.value for item in policy_ir.terminal_safety.allowed_dispositions)
        ),
    ]


def _render_predicate(predicate: FrontierPredicate) -> str:
    value = predicate.value
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, list):
        rendered = ",".join(value)
    else:
        rendered = value
    return f"{predicate.field.value} {predicate.operator.value} {rendered}"


def _parse_predicate(text: str) -> FrontierPredicate:
    field, operator, raw_value = text.split(" ", 2)
    value: str | bool | list[str]
    if raw_value in {"true", "false"}:
        value = raw_value == "true"
    elif operator == FrontierPredicateOperator.in_set.value:
        value = raw_value.split(",")
    else:
        value = raw_value
    return FrontierPredicate(
        field=FrontierPredicateField(field),
        operator=FrontierPredicateOperator(operator),
        value=value,
    )


def _evaluate_condition(
    condition: FrontierConditionExpression,
    state: FrontierEnvironmentState,
) -> bool:
    all_match = all(_evaluate_predicate(predicate, state) for predicate in condition.all_of)
    any_match = not condition.any_of or any(
        _evaluate_predicate(predicate, state) for predicate in condition.any_of
    )
    return all_match and any_match


def _evaluate_predicate(
    predicate: FrontierPredicate,
    state: FrontierEnvironmentState,
) -> bool:
    actual: Any = getattr(state, predicate.field.value)
    if hasattr(actual, "value"):
        actual = actual.value
    if predicate.operator == FrontierPredicateOperator.eq:
        return actual == predicate.value
    if predicate.operator == FrontierPredicateOperator.ne:
        return actual != predicate.value
    return actual in predicate.value


def _evaluate_baselines(authored: Mapping[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    ir_by_ref = {
        row["runtime_ref"]: CanonicalPolicyIR.model_validate(row["policy_ir"])
        for row in authored["policy_ir"]
    }
    env_by_ref = {
        row["runtime_ref"]: FrontierEnvironmentState.model_validate(row)
        for row in authored["environment"]
    }
    runtime_by_ref = {
        row["runtime_ref"]: FrontierRuntimePayload.model_validate(row)
        for row in authored["runtime"]
    }
    topology_by_ref = {row["runtime_ref"]: row for row in authored["topology"]}
    gold_by_ref = {
        row["runtime_ref"]: FrontierGold.model_validate(row)
        for row in authored["gold"]
    }
    rows: list[dict[str, Any]] = []
    for runtime_ref in sorted(runtime_by_ref):
        runtime = runtime_by_ref[runtime_ref]
        state = env_by_ref[runtime_ref]
        gold = gold_by_ref[runtime_ref]
        topology = topology_by_ref[runtime_ref]
        for baseline, parser in (
            ("structured_grammar_parser", structured_grammar_parser),
            ("closed_vocabulary_parser", closed_vocabulary_parser),
        ):
            parsed = parser(runtime.policy_text)
            facts = FrontierRouteFacts(
                parser_status=parsed.status,
                parser_reason=parsed.reason,
                observation_successful=state.observation_successful,
                evidence_authorized=state.evidence_authorized,
                ambiguity_count=(
                    ir_by_ref[runtime_ref].ambiguity.conflict_count
                    if parsed.status != "complete"
                    else 0
                ),
                legal_dispositions=runtime.legal_dispositions,
            )
            route = route_frontier_policy(facts)
            if route.route == "deterministic_parser_compiler":
                assert parsed.parsed_ir is not None
                predicted = compile_policy_ir(parsed.parsed_ir, state).disposition
            else:
                predicted = FrontierDisposition.human_review
            rows.append(
                _baseline_row(
                    runtime_ref,
                    baseline,
                    topology,
                    parsed,
                    route,
                    predicted,
                    gold.disposition,
                )
            )
        for baseline, predicted, route_name in (
            (
                "escalate_all_control",
                FrontierDisposition.human_review,
                "human_escalation",
            ),
            (
                "policy_ir_oracle",
                compile_policy_ir(ir_by_ref[runtime_ref], state).disposition,
                "grader_only_ir_oracle",
            ),
        ):
            rows.append(
                {
                    "runtime_ref": runtime_ref,
                    "baseline": baseline,
                    "capability_class": topology["capability_class"],
                    "policy_family": topology["policy_family"],
                    "pair_id": topology["pair_id"],
                    "pair_kind": topology["pair_kind"],
                    "parser_status": "not_applicable",
                    "route": route_name,
                    "llm_calls": 0,
                    "predicted_disposition": predicted.value,
                    "gold_disposition": gold.disposition.value,
                    "success": predicted == gold.disposition,
                    "unsafe_terminal": False,
                }
            )
    return rows


def _baseline_row(
    runtime_ref: str,
    baseline: str,
    topology: Mapping[str, Any],
    parsed: FrontierParserResult,
    route: FrontierRouteDecision,
    predicted: FrontierDisposition,
    gold: FrontierDisposition,
) -> dict[str, Any]:
    return {
        "runtime_ref": runtime_ref,
        "baseline": baseline,
        "capability_class": topology["capability_class"],
        "policy_family": topology["policy_family"],
        "pair_id": topology["pair_id"],
        "pair_kind": topology["pair_kind"],
        "parser_status": parsed.status,
        "route": route.route,
        "llm_calls": 0,
        "predicted_disposition": predicted.value,
        "gold_disposition": gold.value,
        "success": predicted == gold,
        "unsafe_terminal": (
            topology["capability_class"] == "ambiguous_or_unsafe"
            and predicted != FrontierDisposition.human_review
        ),
    }


def _baseline_manifest(
    rows: Sequence[Mapping[str, Any]],
    topology: Sequence[Mapping[str, Any]],
    gold: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    del gold
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["baseline"])].append(row)
    summaries: dict[str, Any] = {}
    for baseline, baseline_rows in sorted(grouped.items()):
        executed = [row for row in baseline_rows if row["parser_status"] == "complete"]
        errors = [row for row in executed if not row["success"]]
        abstained = [row for row in baseline_rows if row["parser_status"] == "abstain"]
        family_success: dict[str, Any] = {}
        for family in sorted({str(row["policy_family"]) for row in baseline_rows}):
            family_rows = [
                row for row in baseline_rows if row["policy_family"] == family
            ]
            family_success[family] = {
                "case_count": len(family_rows),
                "success_count": sum(bool(row["success"]) for row in family_rows),
                "success_rate": _ratio(
                    sum(bool(row["success"]) for row in family_rows),
                    len(family_rows),
                ),
            }
        pair_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in baseline_rows:
            pair_rows[str(row["pair_id"])].append(row)
        pair_success: dict[str, Any] = {}
        for pair_kind in sorted({str(row["pair_kind"]) for row in baseline_rows}):
            pairs = {
                pair_id: items
                for pair_id, items in pair_rows.items()
                if items[0]["pair_kind"] == pair_kind
            }
            successful_pairs = [
                pair_id
                for pair_id, items in pairs.items()
                if len(items) == 2 and all(bool(item["success"]) for item in items)
            ]
            pair_success[pair_kind] = {
                "pair_count": len(pairs),
                "success_count": len(successful_pairs),
                "success_rate": _ratio(len(successful_pairs), len(pairs)),
                "failure_pair_ids": sorted(set(pairs) - set(successful_pairs)),
            }
        summaries[baseline] = {
            "case_count": len(baseline_rows),
            "success_count": sum(bool(row["success"]) for row in baseline_rows),
            "success_rate": _ratio(
                sum(bool(row["success"]) for row in baseline_rows), len(baseline_rows)
            ),
            "parser_coverage": _ratio(len(executed), len(baseline_rows)),
            "conditional_risk": _ratio(len(errors), len(executed)),
            "parser_abstention_precision": _ratio(
                sum(
                    row["capability_class"] != "symbolic_complete"
                    for row in abstained
                ),
                len(abstained),
            ),
            "unsafe_terminal_count": sum(
                bool(row["unsafe_terminal"]) for row in baseline_rows
            ),
            "llm_calls": sum(int(row["llm_calls"]) for row in baseline_rows),
            "family_success": family_success,
            "counterfactual_pair_success": pair_success,
        }
    symbolic_rows = [
        row
        for row in grouped["structured_grammar_parser"]
        if row["capability_class"] == "symbolic_complete"
    ]
    ambiguous_rows = [
        row
        for row in grouped["structured_grammar_parser"]
        if row["capability_class"] == "ambiguous_or_unsafe"
    ]
    oracle = summaries["policy_ir_oracle"]
    parser_rows = grouped["structured_grammar_parser"]
    capability_parser_metrics: dict[str, Any] = {}
    for capability_class in sorted(
        {str(row["capability_class"]) for row in parser_rows}
    ):
        class_rows = [
            row for row in parser_rows if row["capability_class"] == capability_class
        ]
        capability_parser_metrics[capability_class] = {
            "case_count": len(class_rows),
            "complete_count": sum(
                row["parser_status"] == "complete" for row in class_rows
            ),
            "abstain_count": sum(
                row["parser_status"] == "abstain" for row in class_rows
            ),
            "ambiguous_or_unsafe_count": sum(
                row["parser_status"] in {"ambiguous", "unsafe"} for row in class_rows
            ),
            "parser_coverage": _ratio(
                sum(row["parser_status"] == "complete" for row in class_rows),
                len(class_rows),
            ),
        }
    return {
        "schema_version": "q5-frontier-v5-baseline-manifest-v1",
        "protocol_namespace": "q5-frontier-v5",
        "baseline_rows_sha256": _sha256(_jsonl_bytes(rows)),
        "baseline_summaries": summaries,
        "capability_class_parser_metrics": capability_parser_metrics,
        "acceptance": {
            "policy_ir_oracle_success_count": oracle["success_count"],
            "policy_ir_oracle_case_count": oracle["case_count"],
            "symbolic_complete_parser_coverage": _ratio(
                sum(row["parser_status"] == "complete" for row in symbolic_rows),
                len(symbolic_rows),
            ),
            "symbolic_complete_wrong_execution_count": sum(
                not row["success"] for row in symbolic_rows if row["parser_status"] == "complete"
            ),
            "ambiguous_or_unsafe_unsafe_terminal_count": sum(
                row["unsafe_terminal"] for row in ambiguous_rows
            ),
        },
        "frozen_non_llm_baselines": [
            "structured_grammar_parser",
            "closed_vocabulary_parser",
            "escalate_all_control",
            "policy_ir_oracle",
        ],
        "oracle_deployable": False,
        "parser_weakening_for_headroom_forbidden": True,
        "implementation_source_sha256": _source_inventory(),
        "topology_case_count": len(topology),
    }


def _renderer_manifest(
    runtime_rows: Sequence[Mapping[str, Any]],
    topology_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    renderer_ids = sorted({row["renderer_id"] for row in topology_rows})
    definitions = {
        renderer_id: _hash_payload(
            [
                runtime["policy_text"]
                for runtime, topology in zip(runtime_rows, topology_rows, strict=True)
                if topology["renderer_id"] == renderer_id
            ]
        )
        for renderer_id in renderer_ids
    }
    reserved_test_namespace = "frontier-test-renderer-reserved-v1"
    if reserved_test_namespace in renderer_ids:
        raise ValueError("dev and reserved test renderer namespaces overlap")
    return {
        "schema_version": "q5-frontier-v5-renderer-manifest-v1",
        "protocol_namespace": "q5-frontier-v5",
        "dev_renderer_sha256": definitions,
        "dev_renderer_ids": renderer_ids,
        "reserved_test_renderer_namespace": reserved_test_namespace,
        "reserved_test_renderer_namespace_sha256": _sha256(
            reserved_test_namespace.encode()
        ),
        "dev_test_renderer_reuse_forbidden": True,
        "test_content_created": False,
    }


def _claim_preregistration() -> dict[str, Any]:
    return {
        "schema_version": "q5-frontier-v5-claim-preregistration-v1",
        "protocol_namespace": "q5-frontier-v5",
        "primary_statistical_unit": "distinct_case",
        "k3_semantic_sample_multiplier": False,
        "metrics": {
            "parser_coverage": "complete_parser_cases / distinct_cases",
            "parser_conditional_risk": "wrong_parser_executions / parser_executions",
            "parser_abstention_precision": (
                "appropriate_abstentions / parser_abstentions"
            ),
            "llm_uplift_on_parser_abstained_subset": (
                "llm_success - non_llm_success on identical abstained cases"
            ),
            "non_vacuous_beneficial_case_count": "distinct beneficial cases",
            "beneficial_capture": (
                "captured_beneficial_cases / beneficial_cases; null when denominator=0"
            ),
            "harmful_exposure": "distinct harmful cases exposed to LLM",
            "neutral_exposure": "distinct neutral cases exposed to LLM",
            "hybrid_oracle_regret": "oracle successes - hybrid successes",
            "call_avoidance": "1 - hybrid_calls / llm_only_calls",
            "token_avoidance": "1 - hybrid_tokens / llm_only_tokens",
            "unsafe_action_count": "unsafe terminal actions",
            "invalid_transition_count": "invalid environment transitions",
            "schema_failure_count": "typed IR/schema failures",
            "family_success": "success by policy family",
            "counterfactual_pair_success": "both members correct per pair kind",
        },
        "headline_requirements": {
            "beneficial_case_minimum": 2,
            "beneficial_policy_family_minimum": 2,
            "beneficial_capture_non_vacuous": True,
            "safety_failures_max": 0,
        },
        "semantic_open_parser_failure_required": False,
        "claim_readiness_self_report_allowed": False,
        "readiness": "preregistered_not_evaluated",
        "mock_claims_real_forbidden": True,
        "general_natural_language_extrapolation_forbidden": True,
    }


def _leakage_report(
    runtime_rows: Sequence[Mapping[str, Any]],
    gold_rows: Sequence[Mapping[str, Any]],
    topology_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    runtime_keys = _recursive_keys(runtime_rows)
    leaked_keys = sorted(runtime_keys & _RUNTIME_FORBIDDEN_KEYS)
    runtime_refs = {str(row["runtime_ref"]) for row in runtime_rows}
    gold_refs = {str(row["runtime_ref"]) for row in gold_rows}
    topology_refs = {str(row["runtime_ref"]) for row in topology_rows}
    test_path = Path(__file__).resolve().parents[2] / "data/q5_frontier/test"
    source = inspect.getsource(structured_grammar_parser) + inspect.getsource(
        route_frontier_policy
    )
    compiler_source = inspect.getsource(compile_policy_ir)
    authored = _author_frontier_rows()
    policy_by_ref = {
        row["runtime_ref"]: CanonicalPolicyIR.model_validate(row["policy_ir"])
        for row in authored["policy_ir"]
    }
    environment_by_ref = {
        row["runtime_ref"]: FrontierEnvironmentState.model_validate(row)
        for row in authored["environment"]
    }
    identity_invariant = True
    for runtime_ref, state in environment_by_ref.items():
        original = compile_policy_ir(policy_by_ref[runtime_ref], state).disposition
        rewritten = state.model_copy(
            update={"runtime_ref": "frontier-resource:identity-rewritten"}
        )
        identity_invariant &= (
            compile_policy_ir(policy_by_ref[runtime_ref], rewritten).disposition
            == original
        )
    structured_semantics_invariant = True
    for runtime, topology in zip(runtime_rows, topology_rows, strict=True):
        if topology["capability_class"] != "symbolic_complete":
            continue
        parsed = structured_grammar_parser(str(runtime["policy_text"]))
        structured_semantics_invariant &= (
            parsed.status == "complete"
            and parsed.parsed_ir == policy_by_ref[runtime["runtime_ref"]]
        )
    checks = {
        "runtime_payload_gold_ir_topology_fields_absent": not leaked_keys,
        "runtime_gold_identity_bijection": runtime_refs == gold_refs,
        "runtime_topology_identity_bijection": runtime_refs == topology_refs,
        "dev_test_renderer_families_disjoint": True,
        "q5_frontier_test_absent": not test_path.exists(),
        "identity_rewrite_preserves_compiled_gold": identity_invariant,
        "clause_order_and_irrelevant_comment_preserve_semantics": (
            structured_semantics_invariant
        ),
        "case_specific_expected_action_map_absent": not re.search(
            r"frontier-resource:r\d{3}", source
        ),
        "expected_action_lexicon_absent": "expected_action" not in source,
        "gold_compiler_ignores_case_text_and_expected_tables": not any(
            token in compiler_source
            for token in ("case_id", "policy_text", "expected_action", "expected_disposition")
        ),
        "external_requests": 0,
    }
    return {
        "schema_version": "q5-frontier-v5-leakage-report-v1",
        "protocol_namespace": "q5-frontier-v5",
        "valid": all(value is True or value == 0 for value in checks.values()),
        "checks": checks,
        "leaked_runtime_keys": leaked_keys,
    }


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        result = set(value)
        for item in value.values():
            result |= _recursive_keys(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result: set[str] = set()
        for item in value:
            result |= _recursive_keys(item)
        return result
    return set()


def _source_inventory() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    return {name: _source_sha256(root / name) for name in _SOURCE_FILES}


def _source_sha256(path: Path) -> str:
    """Hash canonical LF source bytes so attestation is checkout-platform stable."""

    return _sha256(path.read_bytes().replace(b"\r\n", b"\n"))


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode()


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _hash_payload(payload: Any) -> str:
    return _sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
