"""Normative Policy IR compiler for Q5 frontier v3.

The compiler has no access to case identity, Gold, topology, renderer labels, or
semantic-family tags.  Scope and temporal applicability are conjunctive policy
guards.  Observation type, host authorization, completion, and ambiguity are
fail-closed safety guards.
"""

from __future__ import annotations

from typing import Any

from app.schemas.q5_frontier import (
    CanonicalPolicyIR,
    FrontierAmbiguityKind,
    FrontierDisposition,
    FrontierPrecedence,
    FrontierPredicate,
    FrontierPredicateOperator,
)
from app.schemas.q5_frontier_v2 import FrontierObservedState
from app.schemas.q5_frontier_v3 import (
    FrontierCompilerResultV3,
    FrontierRuntimePayloadV3,
)


def compile_policy_ir_v3(
    policy_ir: CanonicalPolicyIR,
    runtime_payload: FrontierRuntimePayloadV3,
) -> FrontierCompilerResultV3:
    """Compile typed Policy IR against host-attested runtime facts."""

    observation = runtime_payload.trusted_observation
    state = observation.state
    scope_applicable = bool(state and state.scope in policy_ir.scope.allowed_scopes)
    temporal_applicable = bool(state and state.temporal_state == policy_ir.temporal_state.value)
    observation_type_matches = (
        observation.observation_type.value == policy_ir.evidence_requirements.observation_type
    )
    authorized = bool(
        observation.authorization.authorized and observation.authorization.authorized_evidence_ids
    )
    observation_completed = observation.success and state is not None
    if not (observation_completed and authorized and observation_type_matches):
        return _result(
            FrontierDisposition.human_review,
            scope_applicable,
            temporal_applicable,
            observation_type_matches,
            authorized,
            observation_completed,
            False,
            "safety_guard",
        )
    if policy_ir.ambiguity.kind != FrontierAmbiguityKind.none:
        return _result(
            FrontierDisposition.human_review,
            scope_applicable,
            temporal_applicable,
            observation_type_matches,
            authorized,
            observation_completed,
            False,
            "ambiguity_guard",
        )
    assert state is not None
    all_match = all(_predicate_matches(item, state) for item in policy_ir.condition.all_of)
    any_match = not policy_ir.condition.any_of or any(
        _predicate_matches(item, state) for item in policy_ir.condition.any_of
    )
    base_matches = scope_applicable and temporal_applicable and all_match and any_match
    base = policy_ir.true_disposition if base_matches else policy_ir.false_disposition
    matching_exceptions = [
        clause.disposition
        for clause in policy_ir.exceptions
        if _predicate_matches(clause.predicate, state)
    ]
    exception_matched = bool(matching_exceptions)
    if policy_ir.precedence == FrontierPrecedence.base_only:
        disposition = base
        applied = "base_only"
    elif policy_ir.precedence == FrontierPrecedence.exception_overrides:
        disposition = _unique_exception_or_review(matching_exceptions, base)
        applied = "exception_overrides"
    else:
        disposition = _deny_overrides(base, matching_exceptions)
        applied = "deny_overrides"
    if disposition not in runtime_payload.legal_dispositions:
        disposition = FrontierDisposition.human_review
    return _result(
        disposition,
        scope_applicable,
        temporal_applicable,
        observation_type_matches,
        authorized,
        observation_completed,
        exception_matched,
        applied,
    )


def _predicate_matches(
    predicate: FrontierPredicate,
    state: FrontierObservedState,
) -> bool:
    actual: Any = getattr(state, predicate.field.value)
    if predicate.operator == FrontierPredicateOperator.eq:
        return actual == predicate.value
    if predicate.operator == FrontierPredicateOperator.ne:
        return actual != predicate.value
    if not isinstance(predicate.value, list):  # schema defense in depth
        return False
    return actual in predicate.value


def _unique_exception_or_review(
    matching: list[FrontierDisposition],
    base: FrontierDisposition,
) -> FrontierDisposition:
    if not matching:
        return base
    unique = set(matching)
    return next(iter(unique)) if len(unique) == 1 else FrontierDisposition.human_review


def _deny_overrides(
    base: FrontierDisposition,
    matching: list[FrontierDisposition],
) -> FrontierDisposition:
    candidates = [base, *matching]
    if FrontierDisposition.human_review in candidates:
        return FrontierDisposition.human_review
    if FrontierDisposition.no_action in candidates:
        return FrontierDisposition.no_action
    return base


def _result(
    disposition: FrontierDisposition,
    scope_applicable: bool,
    temporal_applicable: bool,
    observation_type_matches: bool,
    authorized: bool,
    observation_completed: bool,
    exception_matched: bool,
    precedence_applied: str,
) -> FrontierCompilerResultV3:
    return FrontierCompilerResultV3(
        disposition=disposition,
        scope_applicable=scope_applicable,
        temporal_applicable=temporal_applicable,
        observation_type_matches=observation_type_matches,
        authorized=authorized,
        observation_completed=observation_completed,
        exception_matched=exception_matched,
        precedence_applied=precedence_applied,
    )
