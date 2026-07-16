from __future__ import annotations

import inspect
import json

import pytest
from pydantic import ValidationError

from app.eval.q5_frontier_compiler_v3 import compile_policy_ir_v3
from app.eval.q5_frontier_v3 import (
    _author_v3_rows,
    _claim_preregistration,
    build_frontier_v3_artifacts,
    compile_and_grade_v3,
    maximum_possible_claim_headroom,
    run_deterministic_parser_suite_v3,
    verify_compiler_gold_fixtures,
    verify_semantic_candidate_structure,
)
from app.schemas.q5_frontier import CanonicalPolicyIR
from app.schemas.q5_frontier_v3 import (
    FrontierRuntimePayloadV3,
    FrontierSemanticCandidateV3,
)


@pytest.fixture(scope="module")
def v3_rows() -> dict[str, list[dict]]:
    artifacts = build_frontier_v3_artifacts()
    names = (
        "policy_ir.jsonl",
        "runtime_cases.jsonl",
        "topology.jsonl",
        "gold.jsonl",
        "semantic_candidates.jsonl",
        "graded_rows.jsonl",
    )
    return {
        name: [json.loads(line) for line in artifacts[name].decode().splitlines()] for name in names
    }


def test_compiler_is_identity_and_label_independent() -> None:
    source = inspect.getsource(compile_policy_ir_v3).lower()
    for forbidden in (
        "case_id",
        "runtime_ref",
        "gold",
        "topology",
        "pair_id",
        "stratum",
        "renderer",
        "semantic_phenomenon",
    ):
        assert forbidden not in source


def test_independent_handwritten_compiler_gold_has_full_construct_closure() -> None:
    rows = verify_compiler_gold_fixtures("tests/fixtures/q5_frontier_v3/compiler_gold.json")
    assert len(rows) == 51
    by_construct: dict[str, set[str]] = {}
    for row in rows:
        by_construct.setdefault(row["construct"], set()).add(row["polarity"])
    assert all(
        values == {"positive", "negative", "metamorphic"} for values in by_construct.values()
    )
    assert all(row["passed"] for row in rows)


def test_runtime_execution_remains_label_free_and_runtime_only(v3_rows) -> None:
    execution = run_deterministic_parser_suite_v3(v3_rows["runtime_cases.jsonl"])
    assert len(execution) == 64
    forbidden = {
        "gold_disposition",
        "success",
        "policy_family",
        "semantic_phenomenon",
        "pair_id",
        "pair_kind",
        "renderer_id",
        "renderer_distribution",
    }
    assert not any(forbidden & set(row) for row in execution)
    assert list(inspect.signature(run_deterministic_parser_suite_v3).parameters) == ["runtime_rows"]


@pytest.mark.parametrize(
    "mutation",
    ["true_false_swap", "operator_swap", "exception_predicate", "exception_action"],
)
def test_open_language_attestation_proves_structure_not_semantics(v3_rows, mutation: str) -> None:
    candidate_row = next(
        row
        for row in v3_rows["semantic_candidates.jsonl"]
        if not next(
            top for top in v3_rows["topology.jsonl"] if top["runtime_ref"] == row["runtime_ref"]
        )["renderer_id"].startswith("frontier-v3-formal")
    )
    runtime_row = next(
        row
        for row in v3_rows["runtime_cases.jsonl"]
        if row["runtime_ref"] == candidate_row["runtime_ref"]
    )
    sealed_row = next(
        row
        for row in v3_rows["policy_ir.jsonl"]
        if row["runtime_ref"] == candidate_row["runtime_ref"]
    )
    payload = json.loads(json.dumps(candidate_row))
    ir = payload["policy_ir"]
    if mutation == "true_false_swap":
        ir["true_disposition"], ir["false_disposition"] = (
            ir["false_disposition"],
            ir["true_disposition"],
        )
    elif mutation == "operator_swap":
        predicate = ir["condition"]["all_of"][0]
        predicate["operator"] = "ne" if predicate["operator"] == "eq" else "eq"
    elif mutation == "exception_predicate":
        ir["exceptions"][0]["predicate"]["value"] = False
    else:
        ir["exceptions"][0]["disposition"] = "no_action"
    candidate = FrontierSemanticCandidateV3.model_validate(payload)
    runtime = FrontierRuntimePayloadV3.model_validate(runtime_row)
    assert verify_semantic_candidate_structure(runtime, candidate) is True
    assert candidate.policy_ir != CanonicalPolicyIR.model_validate(sealed_row["policy_ir"])


def test_offline_grader_detects_semantic_swap_after_structure_passes() -> None:
    authored = _author_v3_rows()
    candidates = json.loads(json.dumps(authored["semantic_candidates"]))
    target = next(
        row
        for row in candidates
        if not next(
            runtime
            for runtime in authored["runtime_cases"]
            if runtime["runtime_ref"] == row["runtime_ref"]
        )["policy_text"].startswith("Q5POLICYv5;")
    )
    ir = target["policy_ir"]
    ir["true_disposition"], ir["false_disposition"] = (
        ir["false_disposition"],
        ir["true_disposition"],
    )
    execution = run_deterministic_parser_suite_v3(authored["runtime_cases"])
    _, attestations = compile_and_grade_v3(
        execution_rows=execution,
        runtime_rows=authored["runtime_cases"],
        policy_ir_rows=authored["policy_ir"],
        topology_rows=authored["topology"],
        gold_rows=authored["gold"],
        candidate_rows=candidates,
    )
    result = next(row for row in attestations if row["runtime_ref"] == target["runtime_ref"])
    assert result["structural_integrity_verified"] is True
    assert result["semantic_correctness_offline_graded"] is False


@pytest.mark.parametrize(
    "mutation",
    ["scope_omission", "scope_value", "observation_type", "cross_trial_span", "evidence"],
)
def test_closed_binding_and_provenance_mutations_fail_structurally(v3_rows, mutation: str) -> None:
    candidates = v3_rows["semantic_candidates.jsonl"]
    payload = json.loads(json.dumps(candidates[20]))
    runtime_row = next(
        row
        for row in v3_rows["runtime_cases.jsonl"]
        if row["runtime_ref"] == payload["runtime_ref"]
    )
    if mutation == "scope_omission":
        payload["closed_bindings"] = [
            item
            for item in payload["closed_bindings"]
            if item["field_path"] != "scope.allowed_scopes"
        ]
    elif mutation == "scope_value":
        payload["policy_ir"]["scope"]["allowed_scopes"] = ["public"]
    elif mutation == "observation_type":
        current = payload["policy_ir"]["evidence_requirements"]["observation_type"]
        payload["policy_ir"]["evidence_requirements"]["observation_type"] = (
            "inspect_change_state"
            if current != "inspect_change_state"
            else "inspect_incident_state"
        )
    elif mutation == "cross_trial_span":
        donor = candidates[21]["open_provenance"][0]["policy_spans"]
        payload["open_provenance"][0]["policy_spans"] = donor
    else:
        payload["open_provenance"][0]["authorized_evidence_ids"] = ["chunk:foreign"]
    try:
        candidate = FrontierSemanticCandidateV3.model_validate(payload)
    except ValidationError:
        return
    with pytest.raises(ValueError):
        verify_semantic_candidate_structure(
            FrontierRuntimePayloadV3.model_validate(runtime_row), candidate
        )


@pytest.mark.parametrize("mutation", ["abstentions", "families", "phenomena", "conditional_risk"])
def test_claim_headroom_preflight_fails_closed(v3_rows, mutation: str) -> None:
    rows = json.loads(json.dumps(v3_rows["graded_rows.jsonl"]))
    abstained = [row for row in rows if row["parser_status"] == "abstain"]
    if mutation == "abstentions":
        for row in abstained[7:]:
            row["semantic_correctness_offline_graded"] = False
    elif mutation == "families":
        for row in abstained:
            row["policy_family"] = "incident"
    elif mutation == "phenomena":
        for row in abstained:
            row["semantic_phenomenon"] = "single"
    else:
        complete = next(row for row in rows if row["parser_status"] == "complete")
        complete["success"] = False
    receipt = maximum_possible_claim_headroom(rows, _claim_preregistration())
    assert receipt["valid"] is False
    assert receipt["blockers"] == ["claim_headroom"]


def test_authoring_has_no_test_or_external_model_paths() -> None:
    source = inspect.getsource(_author_v3_rows).lower()
    assert "q5_test" not in source
    assert "llm" not in source
    assert "provider" not in source
