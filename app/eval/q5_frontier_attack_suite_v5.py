"""Preregistered deterministic parsers and label-shortcut attacks for K0T."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from app.eval.q5_frontier import structured_grammar_parser
from app.eval.q5_frontier_k0t_contract import (
    K0T_ACTION_PHRASES,
    K0T_ATTACK_THRESHOLD,
)
from app.schemas.q5_frontier_v5 import K0TAttackAudit, K0TAttackResult

PHRASE_TO_ACTION = {
    phrase: disposition.value
    for disposition, phrases in K0T_ACTION_PHRASES.items()
    for phrase in phrases
}


def lexical_condition_action_parser(
    policy_text: str,
    observed_status: str,
) -> str | None:
    """Parse only the preregistered covered prose grammar."""

    match = re.fullmatch(
        r"For an? (incident|change|access|retention) record, when status equals "
        r"([a-z0-9_]+), (.+?); otherwise, (.+?)\.",
        policy_text,
    )
    if not match:
        return None
    true_action = PHRASE_TO_ACTION.get(match.group(3))
    false_action = PHRASE_TO_ACTION.get(match.group(4))
    if true_action is None or false_action is None:
        return None
    return true_action if observed_status == match.group(2) else false_action


def deterministic_parse_k0t(runtime: dict[str, Any]) -> tuple[str, str | None]:
    text = runtime["policy_text"]
    if text.startswith("Q5POLICYv5;"):
        parsed = structured_grammar_parser(text)
        if parsed.status == "complete":
            return "structured_complete", parsed.parsed_ir.model_dump_json()
        return parsed.status, None
    state = runtime["trusted_observation"].get("state")
    if state and lexical_condition_action_parser(text, state["status"]) is not None:
        return "lexical_complete", "terminal_only"
    if "Deliberate conflict:" in text:
        return "ambiguous", None
    return "abstain", None


def evaluate_shortcut_attacks(
    runtime_rows: list[dict[str, Any]],
    topology_rows: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
) -> K0TAttackAudit:
    runtime = {row["runtime_ref"]: row for row in runtime_rows}
    topology = {row["runtime_ref"]: row for row in topology_rows}
    gold = {row["runtime_ref"]: row["disposition"] for row in gold_rows}
    refs = [
        ref
        for ref, row in topology.items()
        if row["capability_class"] == "semantic_open"
    ]
    features = {
        "family_only": {ref: topology[ref]["policy_family"] for ref in refs},
        "phenomenon_only": {
            ref: topology[ref]["semantic_phenomenon"] for ref in refs
        },
        "renderer_template_only": {
            ref: topology[ref]["renderer_id"] for ref in refs
        },
        "token_pattern_state_equality": {
            ref: (
                topology[ref]["policy_family"],
                _state_equality_feature(runtime[ref]),
            )
            for ref in refs
        },
        "action_phrase_omitted": {
            ref: _condition_only_feature(runtime[ref]) for ref in refs
        },
    }
    predictions: dict[str, dict[str, str | None]] = {
        name: _group_majority(feature, gold) for name, feature in features.items()
    }
    predictions["lexical_condition_action_parser"] = {
        ref: lexical_condition_action_parser(
            runtime[ref]["policy_text"],
            runtime[ref]["trusted_observation"]["state"]["status"],
        )
        for ref in refs
    }
    majority = _unique_majority([gold[ref] for ref in refs])
    predictions["majority_action"] = {ref: majority for ref in refs}
    pairs: dict[str, list[str]] = defaultdict(list)
    for ref in refs:
        pairs[topology[ref]["pair_id"]].append(ref)
    neighbor: dict[str, str | None] = {}
    for members in pairs.values():
        if len(members) != 2:
            raise ValueError("semantic pair-neighbor attack requires complete pairs")
        neighbor[members[0]] = gold[members[1]]
        neighbor[members[1]] = gold[members[0]]
    predictions["pair_neighbor"] = neighbor
    attacks = []
    for name, values in predictions.items():
        success = sum(values[ref] == gold[ref] for ref in refs)
        rate = success / len(refs)
        attacks.append(
            K0TAttackResult(
                name=name,
                evaluated_count=len(refs),
                success_count=success,
                success_rate=rate,
                threshold=K0T_ATTACK_THRESHOLD,
                breached=rate > K0T_ATTACK_THRESHOLD,
            )
        )
    return K0TAttackAudit(
        semantic_case_count=len(refs),
        attacks=attacks,
        headroom_survives=not any(item.breached for item in attacks),
    )


def _group_majority(features, gold):
    labels: dict[str, list[str]] = defaultdict(list)
    for ref, feature in features.items():
        labels[str(feature)].append(gold[ref])
    winners = {feature: _unique_majority(values) for feature, values in labels.items()}
    return {ref: winners[str(feature)] for ref, feature in features.items()}


def _unique_majority(values: list[str]) -> str | None:
    counts = Counter(values)
    highest = max(counts.values())
    winners = [label for label, count in counts.items() if count == highest]
    return winners[0] if len(winners) == 1 else None


def _state_equality_feature(runtime):
    observed = runtime["trusted_observation"]["state"]["status"]
    tokens = set(re.findall(r"[a-z][a-z0-9_]*", runtime["policy_text"].lower()))
    return observed in tokens


def _condition_only_feature(runtime):
    text = runtime["policy_text"]
    for phrase in PHRASE_TO_ACTION:
        text = text.replace(phrase, "<ACTION>")
    match = re.search(r"status (?:equals|is|matches) ([a-z0-9_]+)", text)
    if not match:
        return "unparsed"
    return (match.group(1) == runtime["trusted_observation"]["state"]["status"], "<ACTION>")
