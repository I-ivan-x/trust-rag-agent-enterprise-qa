"""Low-complexity parser frozen before K0U development policies exist."""

from __future__ import annotations

import re

from app.eval.q5_frontier_k0t_contract import K0T_ACTION_PHRASES
from app.schemas.q5_frontier import FrontierDisposition
from app.schemas.q5_frontier_v6 import PracticalParserResult, PracticalRuntimeInput

PHRASE_ACTION = {
    phrase: action
    for action, phrases in K0T_ACTION_PHRASES.items()
    for phrase in phrases
}
FIELD_PATTERN = re.compile(r"(status|scope|temporal_state) (eq|ne|in) ([a-z0-9_,]+)")


def preregistered_practical_parser(runtime: PracticalRuntimeInput) -> PracticalParserResult:
    text = runtime.policy_text
    observation = runtime.observation
    if not observation.successful or not observation.authorized:
        return _complete(FrontierDisposition.human_review, "runtime_safety_guard")
    if "Conflict: irreconcilable." in text:
        return PracticalParserResult(status="ambiguous", reason="explicit_conflict")
    required = {
        "Scope rule:": _clause(text, "Scope rule:"),
        "Time rule:": _clause(text, "Time rule:"),
        "Condition all:": _clause(text, "Condition all:"),
        "Condition any:": _clause(text, "Condition any:"),
        "On match:": _clause(text, "On match:"),
        "On miss:": _clause(text, "On miss:"),
        "Exception active:": _clause(text, "Exception active:"),
        "Precedence:": _clause(text, "Precedence:"),
    }
    if any(value is None for value in required.values()):
        return PracticalParserResult(status="abstain", reason="grammar_incomplete")
    scopes = required["Scope rule:"]
    temporal = required["Time rule:"]
    assert scopes is not None and temporal is not None
    applicable = observation.scope in scopes.split(",") and observation.temporal_state == temporal
    all_clause = required["Condition all:"]
    any_clause = required["Condition any:"]
    assert all_clause is not None and any_clause is not None
    all_predicates = _predicates(all_clause)
    any_predicates = _predicates(any_clause) if any_clause != "none" else []
    if all_predicates is None or any_predicates is None:
        return PracticalParserResult(status="abstain", reason="predicate_unsupported")
    condition = all(_matches(item, runtime) for item in all_predicates)
    condition = condition and (
        not any_predicates or any(_matches(item, runtime) for item in any_predicates)
    )
    match_action = _action(required["On match:"])
    miss_action = _action(required["On miss:"])
    exception_action = _action(required["Exception active:"])
    if match_action is None or miss_action is None or exception_action is None:
        return PracticalParserResult(status="abstain", reason="action_unsupported")
    base = match_action if applicable and condition else miss_action
    precedence = required["Precedence:"]
    if observation.exception_active and precedence == "exception_overrides":
        base = exception_action
    if base not in runtime.legal_dispositions:
        return _complete(FrontierDisposition.human_review, "illegal_terminal_guard")
    return _complete(base, "preregistered_practical_complete")


def _clause(text: str, label: str) -> str | None:
    matches = re.findall(rf"(?:^|\n){re.escape(label)} ([^\n]+)\.?(?:\n|$)", text)
    if len(matches) != 1:
        return None
    return matches[0].removesuffix(".")


def _predicates(text: str):
    parts = [item.strip() for item in text.split(", ")]
    parsed = []
    for part in parts:
        match = FIELD_PATTERN.fullmatch(part)
        if not match:
            return None
        value: str | list[str] = match.group(3)
        if match.group(2) == "in":
            value = match.group(3).split(",")
        parsed.append((match.group(1), match.group(2), value))
    return parsed


def _matches(predicate, runtime: PracticalRuntimeInput) -> bool:
    field, operator, expected = predicate
    actual = getattr(runtime.observation, field)
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    return actual in expected


def _action(value: str | None) -> FrontierDisposition | None:
    if value is None:
        return None
    return PHRASE_ACTION.get(value)


def _complete(action: FrontierDisposition, reason: str) -> PracticalParserResult:
    return PracticalParserResult(status="complete", reason=reason, disposition=action)
