from __future__ import annotations

import inspect
import json

import pytest
from pydantic import ValidationError

from app.eval.q5_frontier_v2 import (
    build_frontier_v2_artifacts,
    derive_route_facts,
    generic_clause_parser,
    run_frontier_execution,
    validate_semantic_handoff,
)
from app.schemas.q5_frontier import FrontierDisposition
from app.schemas.q5_frontier_v2 import (
    FrontierParserResultV2,
    FrontierRuntimePayloadV2,
    FrontierSemanticHandoff,
    FrontierTrustedObservation,
)


@pytest.fixture(scope="module")
def frontier_v2_rows() -> dict[str, list[dict]]:
    artifacts = build_frontier_v2_artifacts()
    return {
        name: [json.loads(line) for line in artifacts[name].decode().splitlines()]
        for name in (
            "runtime_cases.jsonl",
            "topology.jsonl",
            "execution_rows.jsonl",
        )
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "success_status",
        "success_state",
        "failure_state",
        "unauthorized_chunks",
        "failure_chunks",
        "extra_field",
    ],
)
def test_trusted_observation_is_closed_and_cross_field_consistent(
    frontier_v2_rows: dict[str, list[dict]], mutation: str
) -> None:
    payload = json.loads(
        json.dumps(frontier_v2_rows["runtime_cases.jsonl"][0]["trusted_observation"])
    )
    if mutation == "success_status":
        payload["status"] = "timeout"
    elif mutation == "success_state":
        payload["state"] = None
    elif mutation == "failure_state":
        payload.update(status="error", success=False)
    elif mutation == "unauthorized_chunks":
        payload["authorization"]["authorized"] = False
    elif mutation == "failure_chunks":
        payload.update(status="error", success=False, state=None)
    else:
        payload["gold"] = "forbidden"
    with pytest.raises(ValidationError):
        FrontierTrustedObservation.model_validate(payload)


def test_route_facts_have_one_runtime_only_derivation_boundary(
    frontier_v2_rows: dict[str, list[dict]],
) -> None:
    runtime_payload = json.loads(
        json.dumps(frontier_v2_rows["runtime_cases.jsonl"][0])
    )
    runtime_payload["trusted_observation"]["authorization"] = {
        "attestation_source": "host_acl",
        "authorized": False,
        "authorized_evidence_ids": [],
    }
    runtime = FrontierRuntimePayloadV2.model_validate(runtime_payload)
    parser = FrontierParserResultV2(
        status="ambiguous",
        reason="conflicting_clauses",
        ambiguity_count=2,
    )
    facts = derive_route_facts(runtime, parser)
    assert facts.host_authorized is False
    assert facts.authorized_evidence_ids == []
    assert facts.parser_ambiguity_count == 2
    source = inspect.getsource(derive_route_facts).lower()
    for forbidden in (
        "gold",
        "topology",
        "stratum",
        "pair_id",
        "policy_ir",
        "required_observations",
    ):
        assert forbidden not in source


def test_execution_rows_are_label_free_and_entrypoint_is_runtime_only(
    frontier_v2_rows: dict[str, list[dict]],
) -> None:
    execution = run_frontier_execution(frontier_v2_rows["runtime_cases.jsonl"][:2])
    assert len(execution) == 8
    forbidden = {
        "gold_disposition",
        "success",
        "capability_class",
        "policy_family",
        "semantic_phenomenon",
        "pair_id",
        "pair_kind",
    }
    assert not any(forbidden & set(row) for row in execution)
    assert list(inspect.signature(run_frontier_execution).parameters) == [
        "runtime_rows"
    ]
    source = inspect.getsource(run_frontier_execution).lower()
    for forbidden_input in (
        "gold_rows",
        "topology_rows",
        "environment_authoring_rows",
        "policy_ir_rows",
    ):
        assert forbidden_input not in source


def test_semantic_open_contains_real_compositional_phenomena_without_forced_failure(
    frontier_v2_rows: dict[str, list[dict]],
) -> None:
    topology = frontier_v2_rows["topology.jsonl"]
    phenomena = {
        row["semantic_phenomenon"]
        for row in topology
        if row["capability_class"] == "semantic_open"
    }
    assert {
        "negation",
        "unless",
        "scope_interaction",
        "temporal_ordering",
        "exception_precedence",
        "exception_precedence_deny",
        "multi_condition_any_all",
        "cross_sentence_reference",
        "deontic_paraphrase",
    } <= phenomena
    runtime_by_ref = {
        row["runtime_ref"]: FrontierRuntimePayloadV2.model_validate(row)
        for row in frontier_v2_rows["runtime_cases.jsonl"]
    }
    semantic = [
        generic_clause_parser(runtime_by_ref[row["runtime_ref"]])
        for row in topology
        if row["capability_class"] == "semantic_open"
    ]
    completed = sum(result.status == "complete" for result in semantic)
    assert 0 < completed < len(semantic)


@pytest.mark.parametrize(
    "mutation",
    [
        "span",
        "action",
        "state",
        "tool",
        "entity",
        "evidence",
    ],
)
def test_semantic_handoff_forgery_fails_closed(
    frontier_v2_rows: dict[str, list[dict]], mutation: str
) -> None:
    runtime_models = [
        FrontierRuntimePayloadV2.model_validate(row)
        for row in frontier_v2_rows["runtime_cases.jsonl"]
    ]
    runtime = next(
        row
        for row in runtime_models
        if not row.policy_text.startswith("Q5POLICYv5;")
        and generic_clause_parser(row).status == "complete"
    )
    parsed = generic_clause_parser(runtime)
    assert parsed.semantic_handoff is not None
    payload = parsed.semantic_handoff.model_dump(mode="json")
    if mutation == "span":
        payload["provenance"][0]["policy_spans"][0]["start"] += 1
    elif mutation == "action":
        payload["action"] = "remediate"
    elif mutation == "state":
        payload["policy_ir"]["condition"]["all_of"][0]["value"] = "forged_state"
    elif mutation == "tool":
        payload["policy_ir"]["condition"]["all_of"][0]["field"] = "tool"
    elif mutation == "entity":
        payload["policy_ir"]["scope"]["resource_type"] = "server"
    else:
        payload["provenance"][0]["authorized_evidence_ids"] = ["chunk:foreign"]
    try:
        handoff = FrontierSemanticHandoff.model_validate(payload)
    except ValidationError:
        return
    with pytest.raises(ValueError):
        validate_semantic_handoff(runtime, handoff)


def test_runtime_model_rejects_all_sealed_or_authoring_fields(
    frontier_v2_rows: dict[str, list[dict]],
) -> None:
    for field in (
        "policy_ir",
        "gold",
        "environment",
        "topology",
        "stratum",
        "pair_id",
        "expected_action",
    ):
        payload = dict(frontier_v2_rows["runtime_cases.jsonl"][0])
        payload[field] = FrontierDisposition.remediate.value
        with pytest.raises(ValidationError):
            FrontierRuntimePayloadV2.model_validate(payload)
