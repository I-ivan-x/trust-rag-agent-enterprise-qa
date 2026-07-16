"""K0R v2: label-free execution and offline grading for the Q5 frontier.

Execution consumes only ``runtime_cases.jsonl``. Sealed Policy IR, authoring
environment rows, Gold, topology, and renderer metadata are accepted only by
the offline authoring/grading functions below.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.eval.q5_symbolic_control import (
    _clauses as v4_symbolic_clauses,
)
from app.eval.q5_symbolic_control import (
    _dispositions as v4_symbolic_dispositions,
)
from app.eval.q5_symbolic_control import (
    _requested_scope as v4_symbolic_requested_scope,
)
from app.schemas.q5_frontier import (
    CanonicalPolicyIR,
    FrontierAmbiguityConflict,
    FrontierAmbiguityKind,
    FrontierConditionExpression,
    FrontierDisposition,
    FrontierEvidenceRequirements,
    FrontierExceptionClause,
    FrontierPolicyScope,
    FrontierPrecedence,
    FrontierPredicate,
    FrontierPredicateField,
    FrontierPredicateOperator,
    FrontierResourceType,
    FrontierTemporalState,
    FrontierTerminalSafetyConstraints,
    compact_policy_ir_schema,
)
from app.schemas.q5_frontier_v2 import (
    FrontierClauseSpan,
    FrontierExecutionRowV2,
    FrontierFieldProvenance,
    FrontierGradedBaselineRowV2,
    FrontierHostAuthorization,
    FrontierObservationStatus,
    FrontierObservationType,
    FrontierObservedState,
    FrontierParserResultV2,
    FrontierRouteDecisionV2,
    FrontierRouteFactsV2,
    FrontierRuntimePayloadV2,
    FrontierSemanticHandoff,
    FrontierTrustedObservation,
)

FRONTIER_V2_SCHEMA = "q5-frontier-v5-dataset-manifest-v2"
FRONTIER_V2_HASHES_SCHEMA = "q5-frontier-v5-hashes-v2"
FRONTIER_V2_CASE_COUNT = 48
FRONTIER_V2_FILES = frozenset(
    {
        "policy_ir.jsonl",
        "environment_authoring.jsonl",
        "runtime_cases.jsonl",
        "topology.jsonl",
        "rendered_meaning.jsonl",
        "gold.jsonl",
        "execution_rows.jsonl",
        "graded_baseline_rows.jsonl",
        "policy_ir_manifest.json",
        "frontier_dataset_manifest.json",
        "renderer_manifest.json",
        "baseline_manifest.json",
        "claim_preregistration.json",
        "leakage_report.json",
        "mutation_matrix.json",
        "frontier_hashes.json",
    }
)
_ALL_DISPOSITIONS = list(FrontierDisposition)
_FAMILY_OBSERVATION: Mapping[FrontierResourceType, FrontierObservationType] = {
    FrontierResourceType.incident: FrontierObservationType.inspect_incident_state,
    FrontierResourceType.change: FrontierObservationType.inspect_change_state,
    FrontierResourceType.access: FrontierObservationType.inspect_access_scope,
    FrontierResourceType.retention: FrontierObservationType.inspect_retention_state,
}
_FAMILY_TRUE_DISPOSITION: Mapping[
    FrontierResourceType, FrontierDisposition
] = {
    FrontierResourceType.incident: FrontierDisposition.remediate,
    FrontierResourceType.change: FrontierDisposition.notify,
    FrontierResourceType.access: FrontierDisposition.notify,
    FrontierResourceType.retention: FrontierDisposition.mark_stale,
}
_FAMILY_DEFAULT_FACT: Mapping[
    FrontierResourceType, tuple[FrontierPredicateField, str, str]
] = {
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
_CRITICAL_PROVENANCE_PATHS = frozenset(
    {
        "scope.resource_type",
        "scope.allowed_scopes",
        "condition.all_of",
        "condition.any_of",
        "temporal_state",
        "exceptions",
        "precedence",
        "evidence_requirements.observation_type",
        "true_disposition",
        "false_disposition",
        "ambiguity",
        "terminal_safety.allowed_dispositions",
    }
)
_RUNTIME_FORBIDDEN_KEYS = frozenset(
    {
        "policy_ir",
        "ir",
        "gold",
        "capability_class",
        "stratum",
        "pair_id",
        "pair_kind",
        "policy_family",
        "semantic_phenomenon",
        "renderer_id",
        "expected_action",
        "expected_disposition",
    }
)
_SOURCE_FILES = (
    "app/eval/q5_frontier.py",
    "app/eval/q5_frontier_v2.py",
    "app/eval/q5_symbolic_control.py",
    "app/schemas/q5_frontier.py",
    "app/schemas/q5_frontier_v2.py",
)


@dataclass(frozen=True)
class _PairSpec:
    family: FrontierResourceType
    capability_class: str
    phenomenon: str
    pair_kind: str
    unsafe_mode: str = "none"


def derive_route_facts(
    runtime_payload: FrontierRuntimePayloadV2,
    parser_result: FrontierParserResultV2,
) -> FrontierRouteFactsV2:
    """The single runtime route-fact derivation boundary."""

    observation = runtime_payload.trusted_observation
    authorization = observation.authorization
    return FrontierRouteFactsV2(
        parser_status=parser_result.status,
        parser_reason=parser_result.reason,
        parser_ambiguity_count=parser_result.ambiguity_count,
        observation_successful=observation.success,
        host_authorized=authorization.authorized,
        authorized_evidence_ids=list(authorization.authorized_evidence_ids),
        legal_dispositions=list(runtime_payload.legal_dispositions),
    )


def route_frontier_policy_v2(
    facts: FrontierRouteFactsV2,
) -> FrontierRouteDecisionV2:
    if (
        not facts.observation_successful
        or not facts.host_authorized
        or facts.parser_status in {"ambiguous", "unsafe"}
        or facts.parser_ambiguity_count > 0
    ):
        return FrontierRouteDecisionV2(
            route="human_escalation",
            llm_allowed=False,
            safe_terminal=FrontierDisposition.human_review,
        )
    if facts.parser_status == "complete":
        return FrontierRouteDecisionV2(
            route="deterministic_parser_compiler", llm_allowed=False
        )
    if facts.parser_status == "abstain" and facts.parser_reason == (
        "incomplete_resolvable"
    ):
        return FrontierRouteDecisionV2(route="llm_semantic_parser", llm_allowed=True)
    return FrontierRouteDecisionV2(
        route="human_escalation",
        llm_allowed=False,
        safe_terminal=FrontierDisposition.human_review,
    )


def validate_semantic_handoff(
    runtime_payload: FrontierRuntimePayloadV2,
    handoff: FrontierSemanticHandoff,
) -> CanonicalPolicyIR:
    """Validate clause provenance, ontology, legal surface, and host evidence."""

    provenance = {item.field_path: item for item in handoff.provenance}
    if set(provenance) != _CRITICAL_PROVENANCE_PATHS:
        raise ValueError("semantic handoff provenance field closure mismatch")
    observation = runtime_payload.trusted_observation
    authorized_ids = set(observation.authorization.authorized_evidence_ids)
    if not observation.success or not observation.authorization.authorized:
        raise ValueError("semantic handoff requires successful authorized observation")
    policy_text = runtime_payload.policy_text
    for field_path, item in provenance.items():
        if not set(item.authorized_evidence_ids) <= authorized_ids:
            raise ValueError(f"semantic provenance uses unauthorized evidence: {field_path}")
        for span in item.policy_spans:
            if span.end > len(policy_text) or policy_text[span.start : span.end] != span.text:
                raise ValueError(f"semantic policy span mismatch: {field_path}")
    policy_ir = handoff.policy_ir
    if policy_ir.evidence_requirements.observation_type != observation.observation_type:
        raise ValueError("semantic handoff forged observation type")
    if not set(policy_ir.terminal_safety.allowed_dispositions) <= set(
        runtime_payload.legal_dispositions
    ):
        raise ValueError("semantic handoff forged legal disposition")
    for predicate in [
        *policy_ir.condition.all_of,
        *policy_ir.condition.any_of,
        *(item.predicate for item in policy_ir.exceptions),
    ]:
        if predicate.field.value not in {
            "status",
            "scope",
            "temporal_state",
            "exception_active",
        }:
            raise ValueError("semantic handoff forged state ontology")
    value_checks = _provenance_value_checks(policy_ir)
    for field_path, values in value_checks.items():
        rendered = " ".join(
            span.text.lower() for span in provenance[field_path].policy_spans
        )
        if any(value.lower() not in rendered for value in values):
            raise ValueError(f"semantic provenance omits field value: {field_path}")
    return policy_ir


def structured_grammar_parser_v2(
    runtime_payload: FrontierRuntimePayloadV2,
) -> FrontierParserResultV2:
    from app.eval.q5_frontier import structured_grammar_parser

    parsed = structured_grammar_parser(runtime_payload.policy_text)
    if parsed.status == "complete":
        return FrontierParserResultV2(
            status="complete",
            reason="structured_complete",
            policy_ir=parsed.parsed_ir,
        )
    if parsed.status == "ambiguous":
        return FrontierParserResultV2(
            status="ambiguous",
            reason="conflicting_clauses",
            ambiguity_count=1,
        )
    return FrontierParserResultV2(
        status="abstain",
        reason=(
            "incomplete_resolvable"
            if parsed.reason == "incomplete_resolvable"
            else "unsupported_construct"
        ),
    )


def generic_clause_parser(
    runtime_payload: FrontierRuntimePayloadV2,
) -> FrontierParserResultV2:
    """Generic clause/regex parser for explicit prose; no renderer metadata."""

    text = runtime_payload.policy_text
    if "CONFLICT[" in text or _contains_direct_conflict(text):
        return FrontierParserResultV2(
            status="ambiguous",
            reason="conflicting_clauses",
            ambiguity_count=2,
        )
    try:
        policy_ir = _parse_explicit_prose(text)
    except ValueError as exc:
        reason = (
            "incomplete_resolvable"
            if str(exc) == "unresolved_reference"
            else "unsupported_construct"
        )
        return FrontierParserResultV2(status="abstain", reason=reason)
    try:
        handoff = _build_semantic_handoff(runtime_payload, policy_ir)
        validate_semantic_handoff(runtime_payload, handoff)
    except ValueError:
        return FrontierParserResultV2(status="abstain", reason="unsupported_construct")
    return FrontierParserResultV2(
        status="complete",
        reason="generic_clause_complete",
        policy_ir=policy_ir,
        semantic_handoff=handoff,
    )


def v4_symbolic_matcher_challenger(
    runtime_payload: FrontierRuntimePayloadV2,
) -> FrontierParserResultV2:
    """Adapter around the frozen v4 clause/disposition/scope matcher."""

    clauses = v4_symbolic_clauses(runtime_payload.policy_text)
    dispositions = [
        disposition
        for clause in clauses
        for disposition in v4_symbolic_dispositions(clause)
    ]
    scopes = [v4_symbolic_requested_scope(clause) for clause in clauses]
    scopes = [scope for scope in scopes if scope is not None]
    if len(set(dispositions)) > 1 or len(set(scopes)) > 1:
        return FrontierParserResultV2(
            status="ambiguous",
            reason="conflicting_clauses",
            ambiguity_count=max(len(set(dispositions)), len(set(scopes))),
        )
    return FrontierParserResultV2(
        status="abstain",
        reason=("incomplete_resolvable" if dispositions else "unsupported_construct"),
    )


def run_frontier_execution(
    runtime_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Produce label-free rows from runtime payloads and parser results only."""

    runtimes = [FrontierRuntimePayloadV2.model_validate(row) for row in runtime_rows]
    parsers: tuple[
        tuple[
            str,
            Callable[[FrontierRuntimePayloadV2], FrontierParserResultV2],
        ],
        ...,
    ] = (
        ("structured_grammar_parser", structured_grammar_parser_v2),
        ("generic_clause_parser", generic_clause_parser),
        ("v4_symbolic_matcher_challenger", v4_symbolic_matcher_challenger),
    )
    rows: list[dict[str, Any]] = []
    for runtime in runtimes:
        for baseline, parser in parsers:
            parsed = parser(runtime)
            facts = derive_route_facts(runtime, parsed)
            decision = route_frontier_policy_v2(facts)
            terminal = FrontierDisposition.human_review
            if decision.route == "deterministic_parser_compiler":
                if parsed.policy_ir is None:
                    raise ValueError("complete execution parser omitted Policy IR")
                terminal = _compile_runtime_disposition(parsed.policy_ir, runtime)
            row = FrontierExecutionRowV2(
                runtime_ref=runtime.runtime_ref,
                baseline=baseline,
                parser_status=parsed.status,
                parser_reason=parsed.reason,
                parser_ambiguity_count=parsed.ambiguity_count,
                route=decision.route,
                llm_allowed=decision.llm_allowed,
                terminal_disposition=terminal,
                parsed_ir_sha256=(
                    _hash_payload(parsed.policy_ir.model_dump(mode="json"))
                    if parsed.policy_ir
                    else None
                ),
                semantic_handoff_sha256=(
                    _hash_payload(parsed.semantic_handoff.model_dump(mode="json"))
                    if parsed.semantic_handoff
                    else None
                ),
            )
            rows.append(row.model_dump(mode="json"))
        rows.append(
            FrontierExecutionRowV2(
                runtime_ref=runtime.runtime_ref,
                baseline="escalate_all_control",
                parser_status="not_applicable",
                parser_reason="not_applicable",
                parser_ambiguity_count=0,
                route="human_escalation",
                llm_allowed=False,
                terminal_disposition=FrontierDisposition.human_review,
            ).model_dump(mode="json")
        )
    return rows


def _parse_explicit_prose(text: str) -> CanonicalPolicyIR:
    resource_match = re.search(
        r"This (incident|change|access|retention) policy applies to scopes ([^.]+)\.",
        text,
    )
    temporal_match = re.search(
        r"Policy temporal state is (current|planned|completed|expired)\.", text
    )
    evidence_match = re.search(
        r"Trusted observation type is (inspect_[a-z_]+)\.", text
    )
    legal_match = re.search(r"Legal dispositions are ([^.]+)\.", text)
    precedence_match = re.search(
        r"Precedence is (exception_overrides|deny_overrides|base_only)\.", text
    )
    exception_match = re.search(
        r"If exception_active is true, ([a-z_]+) overrides the base branch\.",
        text,
    )
    if not all(
        (
            resource_match,
            temporal_match,
            evidence_match,
            legal_match,
            precedence_match,
            exception_match,
        )
    ):
        raise ValueError("unsupported_metadata")
    assert resource_match is not None
    assert temporal_match is not None
    assert evidence_match is not None
    assert legal_match is not None
    assert precedence_match is not None
    assert exception_match is not None
    condition = _parse_condition_clause(text)
    if condition is None:
        if "This condition" in text or "its requirement" in text:
            raise ValueError("unresolved_reference")
        raise ValueError("unsupported_condition")
    all_of, any_of, true_disposition, false_disposition = condition
    return CanonicalPolicyIR(
        scope=FrontierPolicyScope(
            resource_type=FrontierResourceType(resource_match.group(1)),
            allowed_scopes=[
                item.strip() for item in resource_match.group(2).split(",")
            ],
        ),
        condition=FrontierConditionExpression(all_of=all_of, any_of=any_of),
        temporal_state=FrontierTemporalState(temporal_match.group(1)),
        exceptions=[
            FrontierExceptionClause(
                predicate=FrontierPredicate(
                    field=FrontierPredicateField.exception_active,
                    operator=FrontierPredicateOperator.eq,
                    value=True,
                ),
                disposition=FrontierDisposition(exception_match.group(1)),
            )
        ],
        precedence=FrontierPrecedence(precedence_match.group(1)),
        evidence_requirements=FrontierEvidenceRequirements(
            observation_type=evidence_match.group(1)
        ),
        true_disposition=true_disposition,
        false_disposition=false_disposition,
        ambiguity=FrontierAmbiguityConflict(),
        terminal_safety=FrontierTerminalSafetyConstraints(
            allowed_dispositions=[
                FrontierDisposition(item.strip())
                for item in legal_match.group(1).split(",")
            ]
        ),
    )


def _parse_condition_clause(
    text: str,
) -> tuple[
    list[FrontierPredicate],
    list[FrontierPredicate],
    FrontierDisposition,
    FrontierDisposition,
] | None:
    standard = re.search(
        r"When (status|scope|temporal_state) is ([a-z_]+), choose ([a-z_]+); "
        r"otherwise choose ([a-z_]+)\.",
        text,
    )
    if standard:
        return (
            [_predicate(standard.group(1), "eq", standard.group(2))],
            [],
            FrontierDisposition(standard.group(3)),
            FrontierDisposition(standard.group(4)),
        )
    negation = re.search(
        r"When (status|scope|temporal_state) is not ([a-z_]+), choose ([a-z_]+); "
        r"otherwise choose ([a-z_]+)\.",
        text,
    )
    if negation:
        return (
            [_predicate(negation.group(1), "ne", negation.group(2))],
            [],
            FrontierDisposition(negation.group(3)),
            FrontierDisposition(negation.group(4)),
        )
    unless = re.search(
        r"Unless (status|scope|temporal_state) is ([a-z_]+), choose ([a-z_]+); "
        r"otherwise choose ([a-z_]+)\.",
        text,
    )
    if unless:
        return (
            [_predicate(unless.group(1), "ne", unless.group(2))],
            [],
            FrontierDisposition(unless.group(3)),
            FrontierDisposition(unless.group(4)),
        )
    interaction = re.search(
        r"When scope is ([a-z_]+) and status is ([a-z_]+), choose ([a-z_]+); "
        r"otherwise choose ([a-z_]+)\.",
        text,
    )
    if interaction:
        return (
            [
                _predicate("scope", "eq", interaction.group(1)),
                _predicate("status", "eq", interaction.group(2)),
            ],
            [],
            FrontierDisposition(interaction.group(3)),
            FrontierDisposition(interaction.group(4)),
        )
    temporal = re.search(
        r"After temporal_state reaches ([a-z_]+), choose ([a-z_]+); "
        r"before that choose ([a-z_]+)\.",
        text,
    )
    if temporal:
        return (
            [_predicate("temporal_state", "eq", temporal.group(1))],
            [],
            FrontierDisposition(temporal.group(2)),
            FrontierDisposition(temporal.group(3)),
        )
    any_all = re.search(
        r"When status is not ([a-z_]+) and either scope is ([a-z_]+) or scope is "
        r"([a-z_]+), choose ([a-z_]+); otherwise choose ([a-z_]+)\.",
        text,
    )
    if any_all:
        return (
            [_predicate("status", "ne", any_all.group(1))],
            [
                _predicate("scope", "eq", any_all.group(2)),
                _predicate("scope", "eq", any_all.group(3)),
            ],
            FrontierDisposition(any_all.group(4)),
            FrontierDisposition(any_all.group(5)),
        )
    in_set = re.search(
        r"When scope belongs to ([a-z_]+) or ([a-z_]+), choose ([a-z_]+); "
        r"otherwise choose ([a-z_]+)\.",
        text,
    )
    if in_set:
        return (
            [_predicate("scope", "in", [in_set.group(1), in_set.group(2)])],
            [],
            FrontierDisposition(in_set.group(3)),
            FrontierDisposition(in_set.group(4)),
        )
    deontic = re.search(
        r"Upon (status|scope|temporal_state) ([a-z_]+), ([a-z_]+) is obligatory; "
        r"absent that condition, ([a-z_]+) is required\.",
        text,
    )
    if deontic:
        return (
            [_predicate(deontic.group(1), "eq", deontic.group(2))],
            [],
            FrontierDisposition(deontic.group(3)),
            FrontierDisposition(deontic.group(4)),
        )
    return None


def _predicate(
    field: str,
    operator: str,
    value: str | bool | list[str],
) -> FrontierPredicate:
    return FrontierPredicate(
        field=FrontierPredicateField(field),
        operator=FrontierPredicateOperator(operator),
        value=value,
    )


def _build_semantic_handoff(
    runtime_payload: FrontierRuntimePayloadV2,
    policy_ir: CanonicalPolicyIR,
) -> FrontierSemanticHandoff:
    text = runtime_payload.policy_text
    clauses = [item.strip() + "." for item in text.split(".") if item.strip()]

    def find_clause(*needles: str) -> FrontierClauseSpan:
        for clause in clauses:
            lowered = clause.lower()
            if all(needle.lower() in lowered for needle in needles):
                start = text.index(clause)
                return FrontierClauseSpan(
                    start=start,
                    end=start + len(clause),
                    text=clause,
                    sha256=hashlib.sha256(clause.encode()).hexdigest(),
                )
        raise ValueError(f"policy clause provenance missing: {needles}")

    scope_span = find_clause("policy applies to scopes")
    temporal_span = find_clause("policy temporal state")
    condition_span = _condition_span(text)
    exception_span = find_clause("exception_active", "overrides")
    precedence_span = find_clause("precedence is")
    evidence_span = find_clause("trusted observation type")
    safety_span = find_clause("legal dispositions")
    evidence_ids = list(
        runtime_payload.trusted_observation.authorization.authorized_evidence_ids
    )
    mapping = {
        "scope.resource_type": [scope_span],
        "scope.allowed_scopes": [scope_span],
        "condition.all_of": [condition_span],
        "condition.any_of": [condition_span],
        "temporal_state": [temporal_span],
        "exceptions": [exception_span],
        "precedence": [precedence_span],
        "evidence_requirements.observation_type": [evidence_span],
        "true_disposition": [condition_span],
        "false_disposition": [condition_span],
        "ambiguity": [condition_span],
        "terminal_safety.allowed_dispositions": [safety_span],
    }
    return FrontierSemanticHandoff(
        policy_ir=policy_ir,
        provenance=[
            FrontierFieldProvenance(
                field_path=field_path,
                policy_spans=spans,
                authorized_evidence_ids=evidence_ids,
            )
            for field_path, spans in sorted(mapping.items())
        ],
    )


def _condition_span(text: str) -> FrontierClauseSpan:
    for prefix in ("When ", "Unless ", "After ", "Upon "):
        start = text.find(prefix)
        if start >= 0:
            end = text.find(".", start)
            if end < 0:
                break
            clause = text[start : end + 1]
            return FrontierClauseSpan(
                start=start,
                end=end + 1,
                text=clause,
                sha256=hashlib.sha256(clause.encode()).hexdigest(),
            )
    raise ValueError("condition clause span is unresolved")


def _provenance_value_checks(
    policy_ir: CanonicalPolicyIR,
) -> dict[str, list[str]]:
    predicate_values: list[str] = []
    for predicate in [*policy_ir.condition.all_of, *policy_ir.condition.any_of]:
        predicate_values.append(predicate.field.value)
        values = predicate.value if isinstance(predicate.value, list) else [predicate.value]
        predicate_values.extend(str(value).lower() for value in values)
    return {
        "scope.resource_type": [policy_ir.scope.resource_type.value],
        "scope.allowed_scopes": list(policy_ir.scope.allowed_scopes),
        "condition.all_of": [
            item
            for item in predicate_values
            if item
            in " ".join(
                predicate.field.value for predicate in policy_ir.condition.all_of
            )
            or item
            in {
                str(value).lower()
                for predicate in policy_ir.condition.all_of
                for value in (
                    predicate.value
                    if isinstance(predicate.value, list)
                    else [predicate.value]
                )
            }
        ],
        "condition.any_of": [
            str(value).lower()
            for predicate in policy_ir.condition.any_of
            for value in (
                predicate.value
                if isinstance(predicate.value, list)
                else [predicate.value]
            )
        ],
        "temporal_state": [policy_ir.temporal_state.value],
        "exceptions": ["exception_active", "human_review"],
        "precedence": [policy_ir.precedence.value],
        "evidence_requirements.observation_type": [
            str(policy_ir.evidence_requirements.observation_type)
        ],
        "true_disposition": [policy_ir.true_disposition.value],
        "false_disposition": [policy_ir.false_disposition.value],
        "ambiguity": [],
        "terminal_safety.allowed_dispositions": [
            item.value for item in policy_ir.terminal_safety.allowed_dispositions
        ],
    }


def _contains_direct_conflict(text: str) -> bool:
    lowered = text.lower()
    return "requires remediate" in lowered and "forbids remediate" in lowered


def _compile_runtime_disposition(
    policy_ir: CanonicalPolicyIR,
    runtime_payload: FrontierRuntimePayloadV2,
) -> FrontierDisposition:
    observation = runtime_payload.trusted_observation
    if (
        not observation.success
        or not observation.authorization.authorized
        or observation.state is None
        or policy_ir.ambiguity.kind != FrontierAmbiguityKind.none
    ):
        return FrontierDisposition.human_review
    exception_matches = [
        item
        for item in policy_ir.exceptions
        if _evaluate_predicate_v2(item.predicate, observation.state)
    ]
    if exception_matches and policy_ir.precedence in {
        FrontierPrecedence.exception_overrides,
        FrontierPrecedence.deny_overrides,
    }:
        dispositions = {item.disposition for item in exception_matches}
        return (
            next(iter(dispositions))
            if len(dispositions) == 1
            else FrontierDisposition.human_review
        )
    all_match = all(
        _evaluate_predicate_v2(item, observation.state)
        for item in policy_ir.condition.all_of
    )
    any_match = not policy_ir.condition.any_of or any(
        _evaluate_predicate_v2(item, observation.state)
        for item in policy_ir.condition.any_of
    )
    disposition = (
        policy_ir.true_disposition
        if all_match and any_match
        else policy_ir.false_disposition
    )
    return (
        disposition
        if disposition in runtime_payload.legal_dispositions
        else FrontierDisposition.human_review
    )


def _evaluate_predicate_v2(
    predicate: FrontierPredicate,
    state: FrontierObservedState,
) -> bool:
    actual: Any = getattr(state, predicate.field.value)
    if predicate.operator == FrontierPredicateOperator.eq:
        return actual == predicate.value
    if predicate.operator == FrontierPredicateOperator.ne:
        return actual != predicate.value
    return actual in predicate.value


def build_frontier_v2_artifacts() -> dict[str, bytes]:
    authored = _author_v2_rows()
    execution_rows = run_frontier_execution(authored["runtime_cases"])
    graded_rows = grade_frontier_execution(
        execution_rows=execution_rows,
        policy_ir_rows=authored["policy_ir"],
        environment_authoring_rows=authored["environment_authoring"],
        gold_rows=authored["gold"],
        topology_rows=authored["topology"],
        rendered_meaning_rows=authored["rendered_meaning"],
    )
    raw = {
        "policy_ir.jsonl": _jsonl_bytes(authored["policy_ir"]),
        "environment_authoring.jsonl": _jsonl_bytes(
            authored["environment_authoring"]
        ),
        "runtime_cases.jsonl": _jsonl_bytes(authored["runtime_cases"]),
        "topology.jsonl": _jsonl_bytes(authored["topology"]),
        "rendered_meaning.jsonl": _jsonl_bytes(authored["rendered_meaning"]),
        "gold.jsonl": _jsonl_bytes(authored["gold"]),
        "execution_rows.jsonl": _jsonl_bytes(execution_rows),
        "graded_baseline_rows.jsonl": _jsonl_bytes(graded_rows),
    }
    pair_audit = validate_pair_topology(
        policy_ir_rows=authored["policy_ir"],
        environment_authoring_rows=authored["environment_authoring"],
        runtime_rows=authored["runtime_cases"],
        topology_rows=authored["topology"],
        rendered_meaning_rows=authored["rendered_meaning"],
    )
    coverage = _ir_coverage_matrix(
        authored["policy_ir"], authored["environment_authoring"]
    )
    source_inventory = _source_inventory()
    policy_manifest = {
        "schema_version": "q5-frontier-v5-policy-ir-manifest-v2",
        "protocol_namespace": "q5-frontier-v5-k0r",
        "canonical_schema": compact_policy_ir_schema(),
        "canonical_schema_sha256": _hash_payload(compact_policy_ir_schema()),
        "policy_ir_row_count": len(authored["policy_ir"]),
        "policy_ir_sha256": _sha256(raw["policy_ir.jsonl"]),
        "gold_compiler": "sealed_policy_ir_plus_authoring_observation_only",
        "semantic_handoff_schema": "q5-frontier-semantic-handoff-v2",
        "source_sha256": source_inventory,
    }
    topology = authored["topology"]
    dataset_manifest = {
        "schema_version": FRONTIER_V2_SCHEMA,
        "protocol_namespace": "q5-frontier-v5-k0r",
        "namespace": "data/q5_frontier/dev-v2",
        "partition": "dev",
        "case_count": len(authored["runtime_cases"]),
        "capability_class_counts": dict(
            sorted(Counter(item["capability_class"] for item in topology).items())
        ),
        "policy_family_counts": dict(
            sorted(Counter(item["policy_family"] for item in topology).items())
        ),
        "semantic_phenomenon_counts": dict(
            sorted(Counter(item["semantic_phenomenon"] for item in topology).items())
        ),
        "pair_audit": pair_audit,
        "ir_coverage_matrix": coverage,
        "execution_boundary": {
            "input_artifacts": ["runtime_cases.jsonl"],
            "forbidden_execution_inputs": [
                "policy_ir.jsonl",
                "gold.jsonl",
                "environment_authoring.jsonl",
                "topology.jsonl",
                "rendered_meaning.jsonl",
            ],
            "execution_rows_label_free": True,
            "execution_row_count": len(execution_rows),
        },
        "row_sha256": {
            name: _sha256(payload) for name, payload in sorted(raw.items())
        },
    }
    renderer_manifest = _renderer_manifest_v2(
        authored["runtime_cases"], topology, authored["rendered_meaning"]
    )
    baseline_manifest = _baseline_manifest_v2(graded_rows, execution_rows)
    preregistration = _claim_preregistration_v2()
    leakage = _leakage_report_v2(
        runtime_rows=authored["runtime_cases"],
        topology_rows=topology,
        renderer_manifest=renderer_manifest,
    )
    mutation_matrix = _mutation_matrix_v2()
    raw.update(
        {
            "policy_ir_manifest.json": _json_bytes(policy_manifest),
            "frontier_dataset_manifest.json": _json_bytes(dataset_manifest),
            "renderer_manifest.json": _json_bytes(renderer_manifest),
            "baseline_manifest.json": _json_bytes(baseline_manifest),
            "claim_preregistration.json": _json_bytes(preregistration),
            "leakage_report.json": _json_bytes(leakage),
            "mutation_matrix.json": _json_bytes(mutation_matrix),
        }
    )
    raw["frontier_hashes.json"] = _json_bytes(
        {
            "schema_version": FRONTIER_V2_HASHES_SCHEMA,
            "artifacts": {
                name: _sha256(payload) for name, payload in sorted(raw.items())
            },
        }
    )
    if set(raw) != FRONTIER_V2_FILES:
        raise ValueError("frontier v2 artifact closure mismatch")
    return raw


def write_frontier_v2_artifacts(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"frontier v2 output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_frontier_v2_artifacts()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["frontier_dataset_manifest.json"])


def verify_frontier_v2_artifacts(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    actual = {item.name for item in target.iterdir() if item.is_file()}
    if actual != FRONTIER_V2_FILES:
        raise ValueError(
            "frontier v2 artifact closure mismatch: "
            f"missing={sorted(FRONTIER_V2_FILES - actual)}, "
            f"extra={sorted(actual - FRONTIER_V2_FILES)}"
        )
    expected = build_frontier_v2_artifacts()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"frontier v2 recomputation mismatch: {name}")
    return json.loads(expected["frontier_dataset_manifest.json"])


def grade_frontier_execution(
    *,
    execution_rows: Sequence[Mapping[str, Any]],
    policy_ir_rows: Sequence[Mapping[str, Any]],
    environment_authoring_rows: Sequence[Mapping[str, Any]],
    gold_rows: Sequence[Mapping[str, Any]],
    topology_rows: Sequence[Mapping[str, Any]],
    rendered_meaning_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Offline-only join of label-free execution with sealed authoring data."""

    del rendered_meaning_rows
    ir_by_ref = _unique_by_ref(policy_ir_rows, "policy IR")
    environment_by_ref = _unique_by_ref(
        environment_authoring_rows, "authoring environment"
    )
    gold_by_ref = _unique_by_ref(gold_rows, "Gold")
    topology_by_ref = _unique_by_ref(topology_rows, "topology")
    refs = set(ir_by_ref)
    if not (
        refs == set(environment_by_ref) == set(gold_by_ref) == set(topology_by_ref)
    ):
        raise ValueError("offline grading sealed case matrix is incomplete")
    execution_models = [
        FrontierExecutionRowV2.model_validate(item) for item in execution_rows
    ]
    expected_keys = {
        (runtime_ref, baseline)
        for runtime_ref in refs
        for baseline in (
            "structured_grammar_parser",
            "generic_clause_parser",
            "v4_symbolic_matcher_challenger",
            "escalate_all_control",
        )
    }
    actual_keys = {(item.runtime_ref, item.baseline) for item in execution_models}
    if actual_keys != expected_keys or len(execution_models) != len(expected_keys):
        raise ValueError("label-free execution trial matrix mismatch")
    compiled_gold: dict[str, FrontierDisposition] = {}
    for runtime_ref in sorted(refs):
        ir = CanonicalPolicyIR.model_validate(ir_by_ref[runtime_ref]["policy_ir"])
        runtime = FrontierRuntimePayloadV2.model_validate(
            environment_by_ref[runtime_ref]["runtime_payload"]
        )
        disposition = _compile_runtime_disposition(ir, runtime)
        if gold_by_ref[runtime_ref].get("disposition") != disposition.value:
            raise ValueError("sealed Gold does not match deterministic IR compilation")
        compiled_gold[runtime_ref] = disposition
    graded: list[dict[str, Any]] = []
    for execution in execution_models:
        topology = topology_by_ref[execution.runtime_ref]
        gold = compiled_gold[execution.runtime_ref]
        unsafe = (
            gold == FrontierDisposition.human_review
            and execution.terminal_disposition != FrontierDisposition.human_review
        )
        graded.append(
            FrontierGradedBaselineRowV2(
                runtime_ref=execution.runtime_ref,
                baseline=execution.baseline,
                capability_class=topology["capability_class"],
                policy_family=topology["policy_family"],
                semantic_phenomenon=topology["semantic_phenomenon"],
                pair_id=topology["pair_id"],
                pair_kind=topology["pair_kind"],
                parser_status=execution.parser_status,
                route=execution.route,
                llm_calls=execution.llm_calls,
                terminal_disposition=execution.terminal_disposition,
                gold_disposition=gold,
                success=execution.terminal_disposition == gold,
                unsafe_terminal=unsafe,
            ).model_dump(mode="json")
        )
    for runtime_ref in sorted(refs):
        topology = topology_by_ref[runtime_ref]
        gold = compiled_gold[runtime_ref]
        graded.append(
            FrontierGradedBaselineRowV2(
                runtime_ref=runtime_ref,
                baseline="policy_ir_oracle",
                capability_class=topology["capability_class"],
                policy_family=topology["policy_family"],
                semantic_phenomenon=topology["semantic_phenomenon"],
                pair_id=topology["pair_id"],
                pair_kind=topology["pair_kind"],
                parser_status="grader_only",
                route="grader_only_ir_oracle",
                llm_calls=0,
                terminal_disposition=gold,
                gold_disposition=gold,
                success=True,
                unsafe_terminal=False,
            ).model_dump(mode="json")
        )
    return graded


def _author_v2_rows() -> dict[str, list[dict[str, Any]]]:
    outputs: dict[str, list[dict[str, Any]]] = {
        "policy_ir": [],
        "environment_authoring": [],
        "runtime_cases": [],
        "topology": [],
        "rendered_meaning": [],
        "gold": [],
    }
    ordinal = 0
    for pair_ordinal, spec in enumerate(_pair_specs(), start=1):
        pair_id = f"frontier-v2-pair-{pair_ordinal:02d}"
        for member in range(2):
            ordinal += 1
            runtime_ref = f"frontier-v2-resource:r{ordinal:03d}"
            ir, observation = _author_v2_meaning(spec, member, ordinal)
            renderer_id, policy_text, clauses = _render_v2_policy(ir, spec)
            runtime = FrontierRuntimePayloadV2(
                runtime_ref=runtime_ref,
                policy_text=policy_text,
                query=(
                    "Bind the policy to the host-attested observation and select the "
                    "safe governance disposition."
                ),
                legal_dispositions=list(ir.terminal_safety.allowed_dispositions),
                trusted_observation=observation,
            )
            gold = _compile_runtime_disposition(ir, runtime)
            outputs["policy_ir"].append(
                {"runtime_ref": runtime_ref, "policy_ir": ir.model_dump(mode="json")}
            )
            outputs["environment_authoring"].append(
                {
                    "runtime_ref": runtime_ref,
                    "runtime_payload": runtime.model_dump(mode="json"),
                }
            )
            outputs["runtime_cases"].append(runtime.model_dump(mode="json"))
            outputs["topology"].append(
                {
                    "runtime_ref": runtime_ref,
                    "capability_class": spec.capability_class,
                    "policy_family": spec.family.value,
                    "semantic_phenomenon": spec.phenomenon,
                    "pair_id": pair_id,
                    "pair_kind": spec.pair_kind,
                    "renderer_id": renderer_id,
                }
            )
            outputs["rendered_meaning"].append(
                {
                    "runtime_ref": runtime_ref,
                    "renderer_id": renderer_id,
                    "clauses": clauses,
                    "policy_text_sha256": hashlib.sha256(policy_text.encode()).hexdigest(),
                }
            )
            outputs["gold"].append(
                {
                    "runtime_ref": runtime_ref,
                    "disposition": gold.value,
                    "compiler_schema": "q5-frontier-gold-compiler-v2",
                }
            )
    if ordinal != FRONTIER_V2_CASE_COUNT:
        raise ValueError(f"frontier v2 authoring emitted {ordinal} cases")
    return outputs


def _pair_specs() -> list[_PairSpec]:
    specs: list[tuple[FrontierResourceType, str, str, str]] = []
    for family in FrontierResourceType:
        specs.extend(
            [
                (family, "symbolic_complete", "structured_eq", "none"),
                (family, "symbolic_complete", "structured_in", "none"),
            ]
        )
    specs.extend(
        [
            (FrontierResourceType.incident, "semantic_open", "negation", "none"),
            (
                FrontierResourceType.incident,
                "semantic_open",
                "cross_sentence_reference",
                "none",
            ),
            (
                FrontierResourceType.incident,
                "semantic_open",
                "exception_precedence",
                "none",
            ),
            (FrontierResourceType.change, "semantic_open", "unless", "none"),
            (
                FrontierResourceType.change,
                "semantic_open",
                "temporal_ordering",
                "none",
            ),
            (
                FrontierResourceType.change,
                "semantic_open",
                "deontic_paraphrase",
                "none",
            ),
            (
                FrontierResourceType.access,
                "semantic_open",
                "scope_interaction",
                "none",
            ),
            (
                FrontierResourceType.access,
                "semantic_open",
                "multi_condition_any_all",
                "none",
            ),
            (
                FrontierResourceType.retention,
                "semantic_open",
                "in_set_membership",
                "none",
            ),
            (
                FrontierResourceType.retention,
                "semantic_open",
                "exception_precedence_deny",
                "none",
            ),
        ]
    )
    specs.extend(
        [
            (
                FrontierResourceType.incident,
                "ambiguous_or_unsafe",
                "conflicting_clauses",
                "conflict",
            ),
            (
                FrontierResourceType.change,
                "ambiguous_or_unsafe",
                "observation_failure",
                "observation_failure",
            ),
            (
                FrontierResourceType.access,
                "ambiguous_or_unsafe",
                "authorization_denied",
                "authorization",
            ),
            (
                FrontierResourceType.access,
                "ambiguous_or_unsafe",
                "underspecified_scope",
                "conflict",
            ),
            (
                FrontierResourceType.retention,
                "ambiguous_or_unsafe",
                "authorization_denied",
                "authorization",
            ),
            (
                FrontierResourceType.retention,
                "ambiguous_or_unsafe",
                "observation_failure",
                "observation_failure",
            ),
        ]
    )
    if len(specs) != 24:
        raise ValueError("frontier v2 pair spec count is invalid")
    return [
        _PairSpec(
            family=family,
            capability_class=capability,
            phenomenon=phenomenon,
            pair_kind=(
                "policy_fixed_state_changed"
                if index % 2
                else "state_fixed_policy_changed"
            ),
            unsafe_mode=unsafe_mode,
        )
        for index, (family, capability, phenomenon, unsafe_mode) in enumerate(
            specs, start=1
        )
    ]


def _author_v2_meaning(
    spec: _PairSpec,
    member: int,
    ordinal: int,
) -> tuple[CanonicalPolicyIR, FrontierTrustedObservation]:
    field, true_value, false_value = _FAMILY_DEFAULT_FACT[spec.family]
    operator = FrontierPredicateOperator.eq
    all_of: list[FrontierPredicate] | None = None
    any_of: list[FrontierPredicate] = []
    precedence = FrontierPrecedence.base_only
    if spec.phenomenon in {"negation", "unless"}:
        field = FrontierPredicateField.status
        operator = FrontierPredicateOperator.ne
        true_value, false_value = "nominal", "outage"
    elif spec.phenomenon == "scope_interaction":
        all_of = [
            _predicate("scope", "eq", "restricted"),
            _predicate("status", "eq", "outage"),
        ]
        field, true_value, false_value = (
            FrontierPredicateField.status,
            "outage",
            "nominal",
        )
    elif spec.phenomenon == "multi_condition_any_all":
        all_of = [_predicate("status", "ne", "nominal")]
        any_of = [
            _predicate("scope", "eq", "restricted"),
            _predicate("scope", "eq", "production"),
        ]
        field, true_value, false_value = (
            FrontierPredicateField.status,
            "outage",
            "nominal",
        )
    elif spec.phenomenon in {"in_set_membership", "structured_in"}:
        field = FrontierPredicateField.scope
        operator = FrontierPredicateOperator.in_set
        true_value, false_value = "restricted", "public"
    elif spec.phenomenon == "temporal_ordering":
        field = FrontierPredicateField.temporal_state
        true_value, false_value = "planned", "completed"
    elif spec.phenomenon in {
        "exception_precedence",
        "exception_precedence_deny",
    }:
        field = FrontierPredicateField.status
        true_value, false_value = "outage", "nominal"
        precedence = (
            FrontierPrecedence.exception_overrides
            if spec.phenomenon == "exception_precedence"
            else FrontierPrecedence.deny_overrides
        )
    elif spec.phenomenon in {
        "cross_sentence_reference",
        "deontic_paraphrase",
        "conflicting_clauses",
        "underspecified_scope",
        "authorization_denied",
        "observation_failure",
    }:
        field = FrontierPredicateField.status
        true_value, false_value = "outage", "nominal"
    if all_of is None:
        predicate_value: str | list[str] = (
            [true_value, "production"]
            if operator == FrontierPredicateOperator.in_set
            else true_value
        )
        if spec.pair_kind == "state_fixed_policy_changed" and member == 1:
            predicate_value = (
                [false_value, "production"]
                if operator == FrontierPredicateOperator.in_set
                else false_value
            )
        all_of = [
            FrontierPredicate(field=field, operator=operator, value=predicate_value)
        ]
    elif spec.pair_kind == "state_fixed_policy_changed" and member == 1:
        replacement = (
            false_value if all_of[0].value != false_value else true_value
        )
        changed = all_of[0].model_copy(update={"value": replacement})
        all_of = [changed, *all_of[1:]]
    ambiguity = FrontierAmbiguityConflict()
    if spec.unsafe_mode == "conflict":
        ambiguity = FrontierAmbiguityConflict(
            kind=(
                FrontierAmbiguityKind.underspecified_scope
                if spec.phenomenon == "underspecified_scope"
                else FrontierAmbiguityKind.conflicting_clauses
            ),
            conflict_count=2,
        )
    ir = CanonicalPolicyIR(
        scope=FrontierPolicyScope(
            resource_type=spec.family,
            allowed_scopes=["production", "staging", "restricted", "public"],
        ),
        condition=FrontierConditionExpression(all_of=all_of, any_of=any_of),
        temporal_state=(
            FrontierTemporalState.planned
            if spec.phenomenon == "temporal_ordering"
            else FrontierTemporalState.current
        ),
        exceptions=[
            FrontierExceptionClause(
                predicate=_predicate("exception_active", "eq", True),
                disposition=FrontierDisposition.human_review,
            )
        ],
        precedence=precedence,
        evidence_requirements=FrontierEvidenceRequirements(
            observation_type=_FAMILY_OBSERVATION[spec.family].value
        ),
        true_disposition=_FAMILY_TRUE_DISPOSITION[spec.family],
        false_disposition=FrontierDisposition.no_action,
        ambiguity=ambiguity,
        terminal_safety=FrontierTerminalSafetyConstraints(
            allowed_dispositions=list(_ALL_DISPOSITIONS)
        ),
    )
    state_values: dict[str, Any] = {
        "status": "nominal",
        "scope": "production",
        "temporal_state": "current",
        "exception_active": False,
    }
    state_value: Any = true_value
    if spec.pair_kind == "policy_fixed_state_changed" and member == 1:
        state_value = false_value
    if operator == FrontierPredicateOperator.ne:
        state_value = (
            false_value
            if spec.pair_kind == "state_fixed_policy_changed" or member == 0
            else true_value
        )
    if spec.unsafe_mode in {"authorization", "observation_failure"}:
        # Unsafe counterfactuals vary only the attested authorization or the
        # observation completion fact.  Their ordinary state is deliberately
        # held constant so a pair cannot smuggle a second semantic mutation.
        state_value = true_value
    if spec.phenomenon in {
        "exception_precedence",
        "exception_precedence_deny",
    } and spec.pair_kind == "policy_fixed_state_changed":
        state_values["status"] = "outage"
        state_values["exception_active"] = member == 1
    elif field == FrontierPredicateField.temporal_state:
        state_values["temporal_state"] = state_value
    else:
        state_values[field.value] = state_value
    if any_of:
        state_values["scope"] = "restricted"
    authorized = True
    observation_status = FrontierObservationStatus.ok
    if spec.unsafe_mode == "authorization":
        authorized = not (
            spec.pair_kind == "policy_fixed_state_changed" and member == 1
        )
        if spec.pair_kind == "state_fixed_policy_changed":
            authorized = False
    if spec.unsafe_mode == "observation_failure":
        observation_status = (
            FrontierObservationStatus.error
            if spec.pair_kind == "state_fixed_policy_changed" or member == 1
            else FrontierObservationStatus.ok
        )
    success = observation_status in {
        FrontierObservationStatus.ok,
        FrontierObservationStatus.not_found,
    }
    evidence_ids = (
        [f"chunk:v2-c{ordinal:03d}"] if authorized and success else []
    )
    observation = FrontierTrustedObservation(
        observation_type=_FAMILY_OBSERVATION[spec.family],
        status=observation_status,
        success=success,
        authorization=FrontierHostAuthorization(
            authorized=authorized,
            authorized_evidence_ids=evidence_ids,
        ),
        request_id=f"observation:v2-o{ordinal:03d}",
        state=(FrontierObservedState(**state_values) if success else None),
    )
    return ir, observation


def _render_v2_policy(
    ir: CanonicalPolicyIR,
    spec: _PairSpec,
) -> tuple[str, str, list[str]]:
    if spec.capability_class == "symbolic_complete":
        from app.eval.q5_frontier import _structured_clauses

        clauses = _structured_clauses(ir)
        policy_text = "Q5POLICYv5; " + "; ".join(clauses + ["COMMENT neutral"])
        return "frontier-v2-structured-v1", policy_text, clauses
    metadata = [
        (
            f"This {ir.scope.resource_type.value} policy applies to scopes "
            f"{','.join(ir.scope.allowed_scopes)}."
        ),
        f"Policy temporal state is {ir.temporal_state.value}.",
    ]
    condition = _render_semantic_condition(ir, spec.phenomenon)
    exception = (
        "If exception_active is true, human_review overrides the base branch."
    )
    tail = [
        f"Precedence is {ir.precedence.value}.",
        (
            "Trusted observation type is "
            f"{ir.evidence_requirements.observation_type}."
        ),
        (
            "Legal dispositions are "
            + ",".join(item.value for item in ir.terminal_safety.allowed_dispositions)
            + "."
        ),
    ]
    clauses = [*metadata, condition, exception, *tail]
    if spec.unsafe_mode == "conflict":
        conflict_value = ir.condition.all_of[0].value
        condition = (
            "CONFLICT[under status "
            f"{conflict_value}, the policy requires remediate and forbids remediate "
            "while the applicable scope remains unresolved]."
        )
        clauses[2] = condition
    return (
        "frontier-v2-semantic-phenomena-v1",
        " ".join(clauses),
        clauses,
    )


def _render_semantic_condition(ir: CanonicalPolicyIR, phenomenon: str) -> str:
    first = ir.condition.all_of[0]
    true_value = ir.true_disposition.value
    false_value = ir.false_disposition.value
    value = first.value
    if isinstance(value, list):
        values = value
    else:
        values = [str(value)]
    if phenomenon == "negation":
        return (
            f"When {first.field.value} is not {values[0]}, choose {true_value}; "
            f"otherwise choose {false_value}."
        )
    if phenomenon == "unless":
        return (
            f"Unless {first.field.value} is {values[0]}, choose {true_value}; "
            f"otherwise choose {false_value}."
        )
    if phenomenon == "scope_interaction":
        return (
            f"When scope is {ir.condition.all_of[0].value} and status is "
            f"{ir.condition.all_of[1].value}, choose {true_value}; otherwise choose "
            f"{false_value}."
        )
    if phenomenon == "temporal_ordering":
        return (
            f"After temporal_state reaches {values[0]}, choose {true_value}; before "
            f"that choose {false_value}."
        )
    if phenomenon == "multi_condition_any_all":
        return (
            f"When status is not {ir.condition.all_of[0].value} and either scope is "
            f"{ir.condition.any_of[0].value} or scope is "
            f"{ir.condition.any_of[1].value}, choose {true_value}; otherwise choose "
            f"{false_value}."
        )
    if phenomenon == "in_set_membership":
        return (
            f"When scope belongs to {values[0]} or {values[1]}, choose {true_value}; "
            f"otherwise choose {false_value}."
        )
    if phenomenon == "cross_sentence_reference":
        return (
            f"A qualifying incident has {first.field.value} {values[0]}. This condition "
            f"obliges {true_value}; without it, {false_value} applies."
        )
    if phenomenon == "deontic_paraphrase":
        return (
            f"Upon {first.field.value} {values[0]}, {true_value} is obligatory; absent "
            f"that condition, {false_value} is required."
        )
    return (
        f"When {first.field.value} is {values[0]}, choose {true_value}; otherwise "
        f"choose {false_value}."
    )


def validate_pair_topology(
    *,
    policy_ir_rows: Sequence[Mapping[str, Any]],
    environment_authoring_rows: Sequence[Mapping[str, Any]],
    runtime_rows: Sequence[Mapping[str, Any]],
    topology_rows: Sequence[Mapping[str, Any]],
    rendered_meaning_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ir = _unique_by_ref(policy_ir_rows, "pair IR")
    environment = _unique_by_ref(environment_authoring_rows, "pair environment")
    runtime = _unique_by_ref(runtime_rows, "pair runtime")
    topology = _unique_by_ref(topology_rows, "pair topology")
    meaning = _unique_by_ref(rendered_meaning_rows, "pair rendered meaning")
    refs = set(ir)
    if not (refs == set(environment) == set(runtime) == set(topology) == set(meaning)):
        raise ValueError("pair audit case matrix is incomplete")
    pairs: dict[str, list[str]] = defaultdict(list)
    for runtime_ref, row in topology.items():
        pairs[str(row["pair_id"])].append(runtime_ref)
    if len(pairs) != 24 or any(len(items) != 2 for items in pairs.values()):
        raise ValueError("pair audit requires 24 complete pairs")
    policy_fixed = 0
    state_fixed = 0
    for pair_id, pair_refs in sorted(pairs.items()):
        left, right = sorted(pair_refs)
        kind = topology[left]["pair_kind"]
        if topology[right]["pair_kind"] != kind:
            raise ValueError(f"pair kind disagreement: {pair_id}")
        left_ir = ir[left]["policy_ir"]
        right_ir = ir[right]["policy_ir"]
        left_runtime = FrontierRuntimePayloadV2.model_validate(runtime[left])
        right_runtime = FrontierRuntimePayloadV2.model_validate(runtime[right])
        left_state = _semantic_observation_projection(left_runtime.trusted_observation)
        right_state = _semantic_observation_projection(right_runtime.trusted_observation)
        left_clauses = meaning[left]["clauses"]
        right_clauses = meaning[right]["clauses"]
        if kind == "policy_fixed_state_changed":
            policy_fixed += 1
            if left_ir != right_ir:
                raise ValueError(f"policy-fixed pair changed canonical IR: {pair_id}")
            if left_runtime.policy_text != right_runtime.policy_text:
                raise ValueError(f"policy-fixed pair changed rendered meaning: {pair_id}")
            if len(_leaf_differences(left_state, right_state)) != 1:
                raise ValueError(
                    f"policy-fixed pair must change exactly one state fact: {pair_id}"
                )
        elif kind == "state_fixed_policy_changed":
            state_fixed += 1
            if left_state != right_state:
                raise ValueError(f"state-fixed pair changed semantic state: {pair_id}")
            ir_differences = _leaf_differences(left_ir, right_ir)
            if len(ir_differences) != 1:
                raise ValueError(
                    f"state-fixed pair must change exactly one IR leaf: {pair_id}"
                )
            if len(left_clauses) != len(right_clauses) or sum(
                left_clause != right_clause
                for left_clause, right_clause in zip(
                    left_clauses, right_clauses, strict=True
                )
            ) != 1:
                raise ValueError(
                    f"state-fixed pair must change exactly one policy clause: {pair_id}"
                )
        else:
            raise ValueError(f"unsupported pair kind: {kind}")
    if (policy_fixed, state_fixed) != (12, 12):
        raise ValueError("counterfactual pair directions are imbalanced")
    return {
        "pair_count": len(pairs),
        "policy_fixed_state_changed_pair_count": policy_fixed,
        "state_fixed_policy_changed_pair_count": state_fixed,
        "policy_fixed_invariants_valid": True,
        "state_fixed_invariants_valid": True,
    }


def _semantic_observation_projection(
    observation: FrontierTrustedObservation,
) -> dict[str, Any]:
    return {
        "authorized": observation.authorization.authorized,
        # Completion plus its typed payload is one host-attested observation
        # fact. A failed observation has no payload by model invariant.
        "observation": (
            observation.state.model_dump(mode="json") if observation.state else None
        ),
    }


def _leaf_differences(left: Any, right: Any, path: str = "") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, Mapping):
        differences: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                differences.append(child)
            else:
                differences.extend(_leaf_differences(left[key], right[key], child))
        return differences
    if isinstance(left, list):
        if len(left) != len(right):
            return [path]
        differences = []
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            differences.extend(
                _leaf_differences(left_item, right_item, f"{path}[{index}]")
            )
        return differences
    return [] if left == right else [path]


def _ir_coverage_matrix(
    policy_ir_rows: Sequence[Mapping[str, Any]],
    environment_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    irs = [CanonicalPolicyIR.model_validate(item["policy_ir"]) for item in policy_ir_rows]
    runtimes = [
        FrontierRuntimePayloadV2.model_validate(item["runtime_payload"])
        for item in environment_rows
    ]
    operators = Counter(
        predicate.operator.value
        for policy_ir in irs
        for predicate in [*policy_ir.condition.all_of, *policy_ir.condition.any_of]
    )
    precedences = Counter(item.precedence.value for item in irs)
    states = [item.trusted_observation.state for item in runtimes]
    scopes = [item.scope for item in states if item]
    temporal_states = [item.temporal_state for item in states if item]
    coverage = {
        "predicate_operator_counts": dict(sorted(operators.items())),
        "all_of_case_count": sum(bool(item.condition.all_of) for item in irs),
        "any_of_case_count": sum(bool(item.condition.any_of) for item in irs),
        "exception_active_count": sum(item.exception_active for item in states if item),
        "exception_inactive_count": sum(
            not item.exception_active for item in states if item
        ),
        "precedence_counts": dict(sorted(precedences.items())),
        "scope_match_count": sum(scope in {"restricted", "production"} for scope in scopes),
        "scope_mismatch_count": sum(scope in {"public", "staging"} for scope in scopes),
        "temporal_state_counts": dict(sorted(Counter(temporal_states).items())),
        "authorized_count": sum(
            item.trusted_observation.authorization.authorized for item in runtimes
        ),
        "unauthorized_count": sum(
            not item.trusted_observation.authorization.authorized for item in runtimes
        ),
        "observation_success_count": sum(
            item.trusted_observation.success for item in runtimes
        ),
        "observation_failure_count": sum(
            not item.trusted_observation.success for item in runtimes
        ),
    }
    if not {"eq", "ne", "in"} <= set(operators):
        raise ValueError("IR coverage lacks required predicate operators")
    if coverage["any_of_case_count"] == 0:
        raise ValueError("IR coverage lacks any_of")
    if coverage["exception_active_count"] == 0:
        raise ValueError("IR coverage lacks active exception")
    if len(precedences) < 2:
        raise ValueError("IR coverage lacks precedence diversity")
    if not coverage["unauthorized_count"] or not coverage["observation_failure_count"]:
        raise ValueError("IR coverage lacks authorization/observation failures")
    return coverage


def _baseline_manifest_v2(
    graded_rows: Sequence[Mapping[str, Any]],
    execution_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in graded_rows:
        grouped[str(row["baseline"])].append(row)
    summaries: dict[str, Any] = {}
    for baseline, rows in sorted(grouped.items()):
        executed = [item for item in rows if item["parser_status"] == "complete"]
        errors = [item for item in executed if not item["success"]]
        abstained = [item for item in rows if item["parser_status"] == "abstain"]
        semantic = [item for item in rows if item["capability_class"] == "semantic_open"]
        family: dict[str, Any] = {}
        for name in sorted({str(item["policy_family"]) for item in rows}):
            selected = [item for item in rows if item["policy_family"] == name]
            family[name] = _success_summary(selected)
        pair: dict[str, Any] = {}
        for kind in ("policy_fixed_state_changed", "state_fixed_policy_changed"):
            selected = [item for item in rows if item["pair_kind"] == kind]
            by_pair: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
            for item in selected:
                by_pair[str(item["pair_id"])].append(item)
            successes = [
                pair_id
                for pair_id, items in by_pair.items()
                if len(items) == 2 and all(item["success"] for item in items)
            ]
            pair[kind] = {
                "pair_count": len(by_pair),
                "success_count": len(successes),
                "success_rate": _ratio(len(successes), len(by_pair)),
                "failure_pair_ids": sorted(set(by_pair) - set(successes)),
            }
        summaries[baseline] = {
            **_success_summary(rows),
            "parser_coverage": _ratio(len(executed), len(rows)),
            "parser_conditional_risk": _ratio(len(errors), len(executed)),
            "parser_abstention_precision": _ratio(
                sum(item["capability_class"] != "symbolic_complete" for item in abstained),
                len(abstained),
            ),
            "semantic_open": {
                "case_count": len(semantic),
                "complete_count": sum(item["parser_status"] == "complete" for item in semantic),
                "abstain_count": sum(item["parser_status"] == "abstain" for item in semantic),
                "ambiguous_count": sum(item["parser_status"] == "ambiguous" for item in semantic),
                "parser_coverage": _ratio(
                    sum(item["parser_status"] == "complete" for item in semantic),
                    len(semantic),
                ),
                "must_fail_threshold": None,
            },
            "unsafe_terminal_count": sum(item["unsafe_terminal"] for item in rows),
            "family_success": family,
            "counterfactual_pair_success": pair,
            "llm_calls": sum(int(item["llm_calls"]) for item in rows),
        }
    oracle = summaries["policy_ir_oracle"]
    structured = grouped["structured_grammar_parser"]
    symbolic = [
        item for item in structured if item["capability_class"] == "symbolic_complete"
    ]
    ambiguous = [
        item for item in structured if item["capability_class"] == "ambiguous_or_unsafe"
    ]
    return {
        "schema_version": "q5-frontier-v5-baseline-manifest-v2",
        "protocol_namespace": "q5-frontier-v5-k0r",
        "execution_rows_sha256": _sha256(_jsonl_bytes(execution_rows)),
        "graded_rows_sha256": _sha256(_jsonl_bytes(graded_rows)),
        "execution_grading_boundary": "runtime_only_then_offline_sealed_join",
        "baseline_summaries": summaries,
        "acceptance": {
            "policy_ir_oracle_success_count": oracle["success_count"],
            "policy_ir_oracle_case_count": oracle["case_count"],
            "symbolic_complete_parser_coverage": _ratio(
                sum(item["parser_status"] == "complete" for item in symbolic),
                len(symbolic),
            ),
            "symbolic_complete_wrong_execution_count": sum(
                not item["success"] for item in symbolic if item["parser_status"] == "complete"
            ),
            "ambiguous_or_unsafe_unsafe_terminal_count": sum(
                item["unsafe_terminal"] for item in ambiguous
            ),
        },
        "independent_non_llm_baselines": [
            "structured_grammar_parser",
            "generic_clause_parser",
            "v4_symbolic_matcher_challenger",
            "escalate_all_control",
        ],
        "grader_only_upper_bound": "policy_ir_oracle",
        "parser_weakening_for_headroom_forbidden": True,
        "source_sha256": _source_inventory(),
    }


def _success_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    successes = sum(bool(item["success"]) for item in rows)
    return {
        "case_count": len(rows),
        "success_count": successes,
        "success_rate": _ratio(successes, len(rows)),
    }


def _renderer_manifest_v2(
    runtime_rows: Sequence[Mapping[str, Any]],
    topology_rows: Sequence[Mapping[str, Any]],
    meaning_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    renderer_ids = sorted({str(item["renderer_id"]) for item in topology_rows})
    definitions = {
        renderer_id: _hash_payload(
            [
                meaning
                for meaning, topology in zip(
                    meaning_rows, topology_rows, strict=True
                )
                if topology["renderer_id"] == renderer_id
            ]
        )
        for renderer_id in renderer_ids
    }
    coverage = {
        renderer_id: sum(
            item["renderer_id"] == renderer_id for item in topology_rows
        )
        for renderer_id in renderer_ids
    }
    policy_texts = [str(item["policy_text"]) for item in runtime_rows]
    multiplicity = Counter(policy_texts)
    return {
        "schema_version": "q5-frontier-v5-renderer-manifest-v2",
        "protocol_namespace": "q5-frontier-v5-k0r",
        "dev_renderer_sha256": definitions,
        "renderer_coverage": coverage,
        "unique_policy_text_count": len(multiplicity),
        "policy_text_multiplicity": dict(
            sorted(Counter(multiplicity.values()).items())
        ),
        "semantic_boundary_uses_renderer_prefix": False,
        "reserved_test_renderer_namespace": "frontier-test-renderer-reserved-v2",
        "test_renderer_evaluation": {
            "status": "not_evaluated",
            "disjoint": None,
            "reason": "no test renderer or test content exists",
        },
        "test_content_created": False,
    }


def _claim_preregistration_v2() -> dict[str, Any]:
    return {
        "schema_version": "q5-frontier-v5-claim-preregistration-v2",
        "protocol_namespace": "q5-frontier-v5-k0r",
        "primary_statistical_unit": "distinct_case",
        "k3_semantic_sample_multiplier": False,
        "headline_thresholds": {
            "llm_uplift_on_parser_abstained_subset_min": 0.10,
            "parser_conditional_risk_max": 0.0,
            "beneficial_distinct_case_min": 4,
            "beneficial_policy_family_min": 2,
            "beneficial_semantic_phenomenon_min": 2,
            "beneficial_capture_min": 1.0,
            "harmful_exposure_max": 0,
            "hybrid_oracle_regret_max": 0.0,
            "call_avoidance_min": 0.40,
            "token_avoidance_min": 0.35,
            "family_success_min": 0.75,
            "counterfactual_pair_success_min": 0.75,
            "unsafe_action_max": 0,
            "invalid_transition_max": 0,
            "schema_failure_max": 0,
        },
        "metrics": {
            "parser_coverage": "complete parser cases / distinct cases",
            "parser_conditional_risk": "wrong executions / parser executions",
            "parser_abstention_precision": "appropriate abstentions / abstentions",
            "llm_uplift_on_parser_abstained_subset": "paired distinct-case uplift",
            "beneficial_distinct_case_count": "non-vacuous beneficial distinct cases",
            "beneficial_capture": "captured / beneficial; null when denominator is zero",
            "harmful_exposure": "distinct harmful cases exposed to LLM",
            "neutral_exposure": "distinct neutral cases exposed to LLM",
            "hybrid_oracle_regret": "oracle successes minus Hybrid successes",
            "call_avoidance": "1 - Hybrid calls / LLM-only calls",
            "token_avoidance": "1 - Hybrid tokens / LLM-only tokens",
            "family_success": "distinct-case success per policy family",
            "counterfactual_pair_success": "both members correct per pair direction",
            "unsafe_action": "unsafe terminal action count",
            "invalid_transition": "invalid transition count",
            "schema_failure": "typed schema/provenance failure count",
        },
        "semantic_open_parser_failure_required": False,
        "claim_readiness_self_report_allowed": False,
        "readiness": "preregistered_not_evaluated",
        "mock_claims_real_forbidden": True,
        "general_natural_language_extrapolation_forbidden": True,
    }


def _mutation_matrix_v2() -> dict[str, Any]:
    """Declare the independently exercised fail-closed K0R mutations."""

    mutations = {
        "runtime_boundary": [
            "runtime_gold_injection",
            "runtime_topology_injection",
            "unauthorized_chunk_id_injection",
            "ambiguity_sealed_ir_injection",
        ],
        "execution_ledger": [
            "missing_execution_trial",
            "duplicate_execution_trial",
            "extra_execution_trial",
            "execution_label_injection",
        ],
        "semantic_handoff": [
            "forged_policy_span",
            "forged_action",
            "forged_state",
            "forged_tool",
            "forged_entity",
            "unauthorized_evidence",
        ],
        "counterfactual_pairs": [
            "synchronized_policy_fixed_ir_and_render_mutation",
            "synchronized_state_fixed_observation_mutation",
        ],
        "artifact_attestation": [
            "cross_case_ir_transplant",
            "source_hash_forgery",
            "renderer_boundary_downgrade",
            "claim_readiness_self_report",
        ],
    }
    return {
        "schema_version": "q5-frontier-v5-mutation-matrix-v2",
        "protocol_namespace": "q5-frontier-v5-k0r",
        "mutation_count": sum(len(items) for items in mutations.values()),
        "expected_result": "fail_closed",
        "direct_model_validation_and_verifier_covered": True,
        "mutations": mutations,
        "external_requests": 0,
    }


def _leakage_report_v2(
    *,
    runtime_rows: Sequence[Mapping[str, Any]],
    topology_rows: Sequence[Mapping[str, Any]],
    renderer_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_keys = _recursive_keys(runtime_rows)
    leaked_keys = sorted(runtime_keys & _RUNTIME_FORBIDDEN_KEYS)
    parser_source = (
        inspect.getsource(structured_grammar_parser_v2)
        + inspect.getsource(generic_clause_parser)
        + inspect.getsource(v4_symbolic_matcher_challenger)
        + inspect.getsource(derive_route_facts)
        + inspect.getsource(route_frontier_policy_v2)
    )
    non_policy_runtime = [
        {
            key: value
            for key, value in item.items()
            if key not in {"policy_text", "legal_dispositions"}
        }
        for item in runtime_rows
    ]
    action_labels = {item.value for item in FrontierDisposition}
    non_policy_text = json.dumps(non_policy_runtime, sort_keys=True)
    exposed_action_labels = sorted(
        label for label in action_labels if label in non_policy_text
    )
    renderer_coverage = dict(renderer_manifest["renderer_coverage"])
    test_root = Path(__file__).resolve().parents[2] / "data/q5_frontier/test"
    test_status = renderer_manifest["test_renderer_evaluation"]
    checks = {
        "runtime_sealed_fields_absent": not leaked_keys,
        "action_label_exposure_outside_policy_and_legal_surface": (
            not exposed_action_labels
        ),
        "semantic_boundary_renderer_prefix_independent": (
            "renderer_id" not in parser_source
            and "semantic_phenomenon" not in parser_source
        ),
        "host_authorization_typed": all(
            item["trusted_observation"]["authorization"]["attestation_source"]
            == "host_acl"
            for item in runtime_rows
        ),
        "unauthorized_chunk_ids_empty": all(
            item["trusted_observation"]["authorization"]["authorized"]
            or not item["trusted_observation"]["authorization"][
                "authorized_evidence_ids"
            ]
            for item in runtime_rows
        ),
        "execution_entrypoint_runtime_only": list(
            inspect.signature(run_frontier_execution).parameters
        )
        == ["runtime_rows"],
        "q5_frontier_test_absent": not test_root.exists(),
        "external_requests": 0,
    }
    return {
        "schema_version": "q5-frontier-v5-leakage-report-v2",
        "protocol_namespace": "q5-frontier-v5-k0r",
        "valid": all(value is True or value == 0 for value in checks.values()),
        "checks": checks,
        "leaked_runtime_keys": leaked_keys,
        "action_label_exposure": {
            "outside_policy_and_legal_surface": exposed_action_labels,
            "policy_text_disposition_ontology_expected": True,
        },
        "unique_text_template_multiplicity": {
            "unique_policy_text_count": renderer_manifest[
                "unique_policy_text_count"
            ],
            "multiplicity": renderer_manifest["policy_text_multiplicity"],
        },
        "renderer_coverage": renderer_coverage,
        "dev_test_renderer_disjointness": {
            "status": "not_evaluated",
            "passed": None,
            "reason": test_status["reason"],
        },
        "topology_row_count": len(topology_rows),
    }


def _unique_by_ref(
    rows: Sequence[Mapping[str, Any]],
    label: str,
) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        runtime_ref = row.get("runtime_ref")
        if not isinstance(runtime_ref, str) or runtime_ref in output:
            raise ValueError(f"{label} runtime refs are missing or duplicated")
        output[runtime_ref] = row
    return output


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        output = set(value)
        for item in value.values():
            output |= _recursive_keys(item)
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        output: set[str] = set()
        for item in value:
            output |= _recursive_keys(item)
        return output
    return set()


def _source_inventory() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    return {
        name: hashlib.sha256(
            (root / name).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for name in _SOURCE_FILES
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
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
