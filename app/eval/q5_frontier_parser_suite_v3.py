"""Frozen preregistered deterministic parser suite for Q5 frontier v3."""

from __future__ import annotations

import re

from app.eval.q5_frontier import structured_grammar_parser
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
)
from app.schemas.q5_frontier_v3 import FrontierRuntimePayloadV3

ALIASES_V3 = {
    FrontierDisposition.mark_stale: "retire the stale record",
    FrontierDisposition.remediate: "open an intervention ticket",
    FrontierDisposition.notify: "send the designated notice",
    FrontierDisposition.human_review: "transfer the decision to a human reviewer",
    FrontierDisposition.no_action: "leave the governed record unchanged",
}
ALIAS_TO_DISPOSITION_V3 = {value: key for key, value in ALIASES_V3.items()}
DISPOSITION_CODES_V3 = {
    FrontierDisposition.mark_stale: "D1",
    FrontierDisposition.remediate: "D2",
    FrontierDisposition.notify: "D3",
    FrontierDisposition.human_review: "D4",
    FrontierDisposition.no_action: "D5",
}
CODE_TO_DISPOSITION_V3 = {value: key for key, value in DISPOSITION_CODES_V3.items()}


def deterministic_parser_suite_v3(
    runtime: FrontierRuntimePayloadV3,
) -> tuple[str, str, CanonicalPolicyIR | None]:
    """Formal grammar plus only the prose patterns frozen in this module."""

    if runtime.policy_text.startswith("Q5POLICYv5;"):
        result = structured_grammar_parser(runtime.policy_text)
        if result.status == "complete":
            return "complete", "structured_complete", result.parsed_ir
        return result.status, result.reason, None
    if "Conflict status: conflicting_clauses." in runtime.policy_text:
        return "ambiguous", "conflicting_clauses", None
    try:
        parsed = _parse_preregistered_prose(runtime.policy_text)
    except ValueError as exc:
        reason = str(exc)
        return "abstain", ("open_renderer" if reason == "open_renderer" else reason), None
    return "complete", "preregistered_prose_complete", parsed


def parse_closed_bindings_v3(text: str) -> dict[str, list[str]]:
    patterns = {
        "scope.resource_type": r"Resource kind: (incident|change|access|retention)\.",
        "scope.allowed_scopes": r"Permitted scopes exactly: ([a-z_,]+)\.",
        "temporal_state": r"Policy time: (current|planned|completed|expired)\.",
        "evidence_requirements.observation_type": r"Evidence probe: (inspect_[a-z_]+)\.",
        "precedence": r"Precedence mode: (base_only|exception_overrides|deny_overrides)\.",
        "terminal_safety.allowed_dispositions": (r"Terminal codes exactly: ([A-Z0-9,]+)\."),
    }
    output: dict[str, list[str]] = {}
    for path, pattern in patterns.items():
        match = re.search(pattern, text)
        if not match:
            raise ValueError(f"closed binding omitted: {path}")
        values = match.group(1).split(",")
        output[path] = (
            [CODE_TO_DISPOSITION_V3[item].value for item in values]
            if path == "terminal_safety.allowed_dispositions"
            else values
        )
    return output


def _parse_preregistered_prose(text: str) -> CanonicalPolicyIR:
    closed = parse_closed_bindings_v3(text)
    resource = FrontierResourceType(closed["scope.resource_type"][0])
    scopes = closed["scope.allowed_scopes"]
    temporal = FrontierTemporalState(closed["temporal_state"][0])
    precedence = FrontierPrecedence(closed["precedence"][0])
    observation_type = closed["evidence_requirements.observation_type"][0]
    legal = [FrontierDisposition(item) for item in closed["terminal_safety.allowed_dispositions"]]
    standard = re.search(
        r"An eligible record is one whose (status|scope|temporal_state) "
        r"(equals|does not equal|belongs to) ([a-z_,]+)\. That antecedent calls for "
        r"(.+?); otherwise (.+?)\.",
        text,
    )
    temporal_pattern = re.search(
        r"Once observed (status|scope|temporal_state) (eq|ne|in) ([a-z_,]+), "
        r"(.+?) is obligatory; in every other situation, (.+?)\.",
        text,
    )
    if standard:
        operator = {
            "equals": FrontierPredicateOperator.eq,
            "does not equal": FrontierPredicateOperator.ne,
            "belongs to": FrontierPredicateOperator.in_set,
        }[standard.group(2)]
        raw_value = standard.group(3)
        true_disposition = _alias(standard.group(4))
        false_disposition = _alias(standard.group(5))
        field = standard.group(1)
    elif temporal_pattern:
        operator = FrontierPredicateOperator(temporal_pattern.group(2))
        raw_value = temporal_pattern.group(3)
        true_disposition = _alias(temporal_pattern.group(4))
        false_disposition = _alias(temporal_pattern.group(5))
        field = temporal_pattern.group(1)
    else:
        raise ValueError("open_renderer")
    value: str | list[str] = (
        raw_value.split(",") if operator == FrontierPredicateOperator.in_set else raw_value
    )
    ambiguity = (
        FrontierAmbiguityConflict(kind=FrontierAmbiguityKind.conflicting_clauses, conflict_count=2)
        if "Conflict status: conflicting_clauses." in text
        else FrontierAmbiguityConflict()
    )
    return CanonicalPolicyIR(
        scope=FrontierPolicyScope(resource_type=resource, allowed_scopes=scopes),
        condition=FrontierConditionExpression(
            all_of=[
                FrontierPredicate(
                    field=FrontierPredicateField(field),
                    operator=operator,
                    value=value,
                )
            ]
        ),
        temporal_state=temporal,
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
        precedence=precedence,
        evidence_requirements=FrontierEvidenceRequirements(observation_type=observation_type),
        true_disposition=true_disposition,
        false_disposition=false_disposition,
        ambiguity=ambiguity,
        terminal_safety=FrontierTerminalSafetyConstraints(allowed_dispositions=legal),
    )


def _alias(value: str) -> FrontierDisposition:
    try:
        return ALIAS_TO_DISPOSITION_V3[value]
    except KeyError as exc:
        raise ValueError("open_renderer") from exc
