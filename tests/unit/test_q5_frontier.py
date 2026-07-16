from __future__ import annotations

import inspect
import json

import pytest
from pydantic import ValidationError

from app.eval.q5_frontier import (
    build_frontier_artifacts,
    closed_vocabulary_parser,
    compile_policy_ir,
    route_frontier_policy,
    structured_grammar_parser,
    validate_semantic_policy_ir,
)
from app.schemas.q5_frontier import (
    CanonicalPolicyIR,
    FrontierDisposition,
    FrontierEnvironmentState,
    FrontierRouteFacts,
    compact_policy_ir_schema,
)


@pytest.fixture(scope="module")
def frontier_rows() -> dict[str, list[dict]]:
    artifacts = build_frontier_artifacts()
    return {
        name: [json.loads(line) for line in artifacts[name].decode().splitlines()]
        for name in (
            "policy_ir.jsonl",
            "environment.jsonl",
            "runtime_cases.jsonl",
            "topology.jsonl",
            "gold.jsonl",
        )
    }


def test_policy_ir_schema_is_pydantic_derived_and_closed() -> None:
    schema = compact_policy_ir_schema()
    assert schema["additionalProperties"] is False
    assert "title" not in json.dumps(schema)
    assert "default" not in json.dumps(schema)
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False


def test_runtime_and_router_models_reject_grader_fields(frontier_rows) -> None:
    runtime = dict(frontier_rows["runtime_cases.jsonl"][0])
    runtime["gold"] = {"disposition": "remediate"}
    from app.schemas.q5_frontier import FrontierRuntimePayload

    with pytest.raises(ValidationError):
        FrontierRuntimePayload.model_validate(runtime)
    with pytest.raises(ValidationError):
        FrontierRouteFacts.model_validate(
            {
                "parser_status": "complete",
                "parser_reason": "canonical_complete",
                "observation_successful": True,
                "evidence_authorized": True,
                "ambiguity_count": 0,
                "legal_dispositions": list(FrontierDisposition),
                "case_id": "forbidden",
            }
        )


def test_gold_compilation_is_identity_and_text_independent(frontier_rows) -> None:
    ir = CanonicalPolicyIR.model_validate(
        frontier_rows["policy_ir.jsonl"][0]["policy_ir"]
    )
    state = FrontierEnvironmentState.model_validate(
        frontier_rows["environment.jsonl"][0]
    )
    original = compile_policy_ir(ir, state)
    rewritten = state.model_copy(
        update={"runtime_ref": "frontier-resource:rewritten-identity"}
    )
    assert compile_policy_ir(ir, rewritten).disposition == original.disposition
    compiler_source = inspect.getsource(compile_policy_ir)
    assert "case_id" not in compiler_source
    assert "policy_text" not in compiler_source
    assert "expected_action" not in compiler_source


def test_clause_order_and_irrelevant_comment_preserve_typed_ir(frontier_rows) -> None:
    symbolic = next(
        (runtime, topology, policy)
        for runtime, topology, policy in zip(
            frontier_rows["runtime_cases.jsonl"],
            frontier_rows["topology.jsonl"],
            frontier_rows["policy_ir.jsonl"],
            strict=True,
        )
        if topology["capability_class"] == "symbolic_complete"
    )
    runtime, _, policy = symbolic
    parsed = structured_grammar_parser(runtime["policy_text"])
    assert parsed.status == "complete"
    assert parsed.parsed_ir == CanonicalPolicyIR.model_validate(policy["policy_ir"])
    clauses = runtime["policy_text"].split(";")
    transformed = ";".join([clauses[0], *reversed(clauses[1:]), " COMMENT harmless"])
    transformed_parsed = structured_grammar_parser(transformed)
    assert transformed_parsed.status == "complete"
    assert transformed_parsed.parsed_ir == parsed.parsed_ir


@pytest.mark.parametrize(
    ("text", "status", "reason"),
    [
        (
            "Q5POLICYv5; RESOURCE incident; NOT status eq outage",
            "abstain",
            "unsupported_construct",
        ),
        (
            "CONFLICT[remediate and do not remediate]",
            "ambiguous",
            "conflicting_clauses",
        ),
        ("unknown natural construct", "abstain", "incomplete_resolvable"),
    ],
)
def test_unknown_negation_and_conflict_abstain(
    text: str, status: str, reason: str
) -> None:
    result = structured_grammar_parser(text)
    assert (result.status, result.reason) == (status, reason)


def test_parser_first_router_has_three_strict_capability_branches() -> None:
    legal = list(FrontierDisposition)
    complete = route_frontier_policy(
        FrontierRouteFacts(
            parser_status="complete",
            parser_reason="canonical_complete",
            observation_successful=True,
            evidence_authorized=True,
            ambiguity_count=0,
            legal_dispositions=legal,
        )
    )
    open_semantics = route_frontier_policy(
        FrontierRouteFacts(
            parser_status="abstain",
            parser_reason="incomplete_resolvable",
            observation_successful=True,
            evidence_authorized=True,
            ambiguity_count=0,
            legal_dispositions=legal,
        )
    )
    unsafe = route_frontier_policy(
        FrontierRouteFacts(
            parser_status="complete",
            parser_reason="canonical_complete",
            observation_successful=True,
            evidence_authorized=False,
            ambiguity_count=0,
            legal_dispositions=legal,
        )
    )
    assert (complete.route, complete.llm_allowed) == (
        "deterministic_parser_compiler",
        False,
    )
    assert (open_semantics.route, open_semantics.llm_allowed) == (
        "llm_semantic_parser",
        True,
    )
    assert (
        unsafe.route,
        unsafe.llm_allowed,
        unsafe.terminal_disposition,
    ) == ("human_escalation", False, FrontierDisposition.human_review)
    router_source = inspect.getsource(route_frontier_policy)
    for forbidden in (
        "case_id",
        "runtime_ref",
        "stratum",
        "gold",
        "policy_family",
        "pair_id",
        "expected_disposition",
    ):
        assert forbidden not in router_source.lower()


def test_closed_vocabulary_control_and_formal_parser_share_the_core(
    frontier_rows,
) -> None:
    for runtime, topology in zip(
        frontier_rows["runtime_cases.jsonl"],
        frontier_rows["topology.jsonl"],
        strict=True,
    ):
        if topology["capability_class"] == "symbolic_complete":
            assert closed_vocabulary_parser(
                runtime["policy_text"]
            ) == structured_grammar_parser(runtime["policy_text"])


def test_future_llm_semantic_parse_must_pass_canonical_ir(frontier_rows) -> None:
    payload = frontier_rows["policy_ir.jsonl"][0]["policy_ir"]
    accepted = validate_semantic_policy_ir(payload)
    assert accepted.status == "complete"
    assert accepted.reason == "semantic_typed_complete"
    forged = json.loads(json.dumps(payload))
    forged["expected_action"] = "remediate"
    rejected = validate_semantic_policy_ir(forged)
    assert (rejected.status, rejected.reason) == (
        "abstain",
        "unsupported_construct",
    )
