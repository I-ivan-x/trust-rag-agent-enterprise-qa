"""Deterministic suite frozen before parser-uncovered-dev authoring.

The suite is intentionally closed vocabulary.  It exposes four independent
parsers and a conflict-aware best-of selector.  It never reads identity,
topology, authored IR, or Gold.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.eval.q5_boundary_b import _ordinary_controlled_prose_parser
from app.eval.q5_frontier import structured_grammar_parser
from app.eval.q5_frontier_parser_suite_v3 import (
    ALIAS_TO_DISPOSITION_V3,
    parse_closed_bindings_v3,
)
from app.schemas.q5_frontier import (
    CanonicalPolicyIR,
    FrontierAmbiguityConflict,
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
from app.schemas.q5_frontier_v4 import FrontierParserOutcomeV4, FrontierRuntimePayloadV4

Parser = Callable[[FrontierRuntimePayloadV4], FrontierParserOutcomeV4]


def structured_parser(runtime: FrontierRuntimePayloadV4) -> FrontierParserOutcomeV4:
    if not runtime.policy_text.startswith("Q5POLICYv5;"):
        return _abstain("structured_parser", "not_structured")
    parsed = structured_grammar_parser(runtime.policy_text)
    if parsed.status != "complete":
        return _abstain("structured_parser", parsed.reason)
    return _complete("structured_parser", "structured_complete", parsed.parsed_ir)


def boundary_b_parser(runtime: FrontierRuntimePayloadV4) -> FrontierParserOutcomeV4:
    parsed, extension = _ordinary_controlled_prose_parser(runtime)
    if parsed is None:
        return _abstain("boundary_b_parser", "not_boundary_b_prose")
    reason = "cross_sentence_complete" if extension else "generic_clause_complete"
    return _complete("boundary_b_parser", reason, parsed)


def compositional_challenger(
    runtime: FrontierRuntimePayloadV4,
) -> FrontierParserOutcomeV4:
    """Post-hoc v3 challenger: four explicit compositional prose forms."""

    text = runtime.policy_text
    try:
        closed = parse_closed_bindings_v3(text)
    except (KeyError, ValueError):
        return _abstain("compositional_challenger", "closed_bindings_incomplete")
    parsed = (
        _cross_sentence(text)
        or _nested_exception(text)
        or _negation_scope(text)
        or _temporal_obligation(text)
    )
    if parsed is None:
        return _abstain("compositional_challenger", "not_frozen_compositional_form")
    all_of, any_of, true_value, false_value = parsed
    try:
        policy_ir = _policy_ir(closed, all_of, any_of, true_value, false_value)
    except (KeyError, ValueError):
        return _abstain("compositional_challenger", "normalization_failed")
    return _complete(
        "compositional_challenger", "frozen_compositional_complete", policy_ir
    )


def alias_condition_normalizer(
    runtime: FrontierRuntimePayloadV4,
) -> FrontierParserOutcomeV4:
    """Closed alias/condition normalizer preregistered without future renderers."""

    text = runtime.policy_text
    try:
        closed = parse_closed_bindings_v3(text)
    except (KeyError, ValueError):
        return _abstain("alias_condition_normalizer", "closed_bindings_incomplete")
    pattern = re.search(
        r"Provided (status|scope|temporal_state) is (equal to|other than|one of) "
        r"([a-z_,]+), the policy directs (.+?); failing that, it directs (.+?)\.",
        text,
    )
    if not pattern:
        return _abstain("alias_condition_normalizer", "not_normalizer_form")
    operator = {
        "equal to": FrontierPredicateOperator.eq,
        "other than": FrontierPredicateOperator.ne,
        "one of": FrontierPredicateOperator.in_set,
    }[pattern.group(2)]
    raw: str | list[str] = pattern.group(3)
    if operator == FrontierPredicateOperator.in_set:
        raw = raw.split(",")
    predicate = FrontierPredicate(
        field=FrontierPredicateField(pattern.group(1)), operator=operator, value=raw
    )
    try:
        policy_ir = _policy_ir(
            closed, [predicate], [], pattern.group(4), pattern.group(5)
        )
    except (KeyError, ValueError):
        return _abstain("alias_condition_normalizer", "normalization_failed")
    return _complete(
        "alias_condition_normalizer", "alias_condition_complete", policy_ir
    )


def best_of_deterministic_selector(
    runtime: FrontierRuntimePayloadV4,
) -> FrontierParserOutcomeV4:
    complete = [
        item
        for parser in FROZEN_COMPONENT_PARSERS
        if (item := parser(runtime)).status == "complete"
    ]
    if not complete:
        return _abstain("best_of_deterministic_selector", "suite_abstained")
    canonical = {item.policy_ir.model_dump_json() for item in complete if item.policy_ir}
    if len(canonical) != 1:
        return FrontierParserOutcomeV4(
            status="ambiguous",
            reason="deterministic_parser_conflict",
            parser_name="best_of_deterministic_selector",
        )
    return _complete(
        "best_of_deterministic_selector",
        "best_of_complete:" + ",".join(item.parser_name for item in complete),
        complete[0].policy_ir,
    )


FROZEN_COMPONENT_PARSERS: tuple[Parser, ...] = (
    structured_parser,
    boundary_b_parser,
    compositional_challenger,
    alias_condition_normalizer,
)


def _cross_sentence(text: str):
    match = re.search(
        r"A record qualifies whenever its (status|scope|temporal_state) corresponds to "
        r"([a-z_]+)(?: and at least one of status equal to ([a-z_]+) or "
        r"exception_active equal to (true|false))?\. What was just described makes "
        r"it proper to (.+?); without that fact, (.+?)\.",
        text,
    )
    if not match:
        return None
    all_of = [_predicate(match.group(1), "eq", match.group(2))]
    any_of = []
    if match.group(3):
        any_of = [
            _predicate("status", "eq", match.group(3)),
            _predicate("exception_active", "eq", match.group(4) == "true"),
        ]
    return all_of, any_of, match.group(5), match.group(6)


def _nested_exception(text: str):
    match = re.search(
        r"Ordinarily, a (status|scope|temporal_state) of ([a-z_]+) supports the course "
        r"to (.+?)(?: together with (status|scope|temporal_state) equal to ([a-z_]+))?, "
        r"with (.+?) as the alternative\.",
        text,
    )
    if not match:
        return None
    all_of = [_predicate(match.group(1), "eq", match.group(2))]
    if match.group(4):
        all_of.append(_predicate(match.group(4), "eq", match.group(5)))
    return all_of, [], match.group(3), match.group(6)


def _negation_scope(text: str):
    match = re.search(
        r"it is not the case that (status|scope|temporal_state) may be ([a-z_]+); "
        r"while that negated condition holds, (.+?), or else (.+?)\.",
        text,
    )
    if not match:
        return None
    return [_predicate(match.group(1), "ne", match.group(2))], [], match.group(3), match.group(4)


def _temporal_obligation(text: str):
    match = re.search(
        r"observing (status|scope|temporal_state) as ([a-z_]+) creates an obligation "
        r"to (.+?)\. Before the combined time-and-scope condition is satisfied, (.+?)\.",
        text,
    )
    if not match:
        return None
    return [_predicate(match.group(1), "eq", match.group(2))], [], match.group(3), match.group(4)


def _policy_ir(closed, all_of, any_of, true_value, false_value):
    true_disposition = ALIAS_TO_DISPOSITION_V3[true_value]
    false_disposition = ALIAS_TO_DISPOSITION_V3[false_value]
    return CanonicalPolicyIR(
        scope=FrontierPolicyScope(
            resource_type=FrontierResourceType(closed["scope.resource_type"][0]),
            allowed_scopes=closed["scope.allowed_scopes"],
        ),
        condition=FrontierConditionExpression(all_of=all_of, any_of=any_of),
        temporal_state=FrontierTemporalState(closed["temporal_state"][0]),
        exceptions=[
            FrontierExceptionClause(
                predicate=_predicate("exception_active", "eq", True),
                disposition=FrontierDisposition.human_review,
            )
        ],
        precedence=FrontierPrecedence(closed["precedence"][0]),
        evidence_requirements=FrontierEvidenceRequirements(
            observation_type=closed["evidence_requirements.observation_type"][0]
        ),
        true_disposition=true_disposition,
        false_disposition=false_disposition,
        ambiguity=FrontierAmbiguityConflict(),
        terminal_safety=FrontierTerminalSafetyConstraints(
            allowed_dispositions=[
                FrontierDisposition(item)
                for item in closed["terminal_safety.allowed_dispositions"]
            ]
        ),
    )


def _predicate(field, operator, value):
    return FrontierPredicate(
        field=FrontierPredicateField(field),
        operator=FrontierPredicateOperator(operator),
        value=value,
    )


def _complete(name, reason, policy_ir):
    assert policy_ir is not None
    return FrontierParserOutcomeV4(
        status="complete", reason=reason, parser_name=name, policy_ir=policy_ir
    )


def _abstain(name, reason):
    return FrontierParserOutcomeV4(status="abstain", reason=reason, parser_name=name)
