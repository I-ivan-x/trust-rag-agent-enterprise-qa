"""K0S v3 semantic frontier with preregistered deterministic parser attacks."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.eval.q5_frontier import _structured_clauses, structured_grammar_parser
from app.eval.q5_frontier_compiler_v3 import compile_policy_ir_v3
from app.eval.q5_frontier_parser_suite_v3 import (
    ALIASES_V3 as _ALIASES,
)
from app.eval.q5_frontier_parser_suite_v3 import (
    DISPOSITION_CODES_V3 as _DISPOSITION_CODES,
)
from app.eval.q5_frontier_parser_suite_v3 import (
    deterministic_parser_suite_v3,
    parse_closed_bindings_v3,
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
)
from app.schemas.q5_frontier_v2 import (
    FrontierClauseSpan,
    FrontierHostAuthorization,
    FrontierObservationStatus,
    FrontierObservationType,
    FrontierObservedState,
    FrontierTrustedObservation,
)
from app.schemas.q5_frontier_v3 import (
    FrontierAttestationV3,
    FrontierClosedBindingV3,
    FrontierExecutionRowV3,
    FrontierGradedRowV3,
    FrontierOpenFieldProvenanceV3,
    FrontierRuntimePayloadV3,
    FrontierSemanticCandidateV3,
)

FRONTIER_V3_CASE_COUNT = 64
FRONTIER_V3_FILES = frozenset(
    {
        "policy_ir.jsonl",
        "environment_authoring.jsonl",
        "runtime_cases.jsonl",
        "topology.jsonl",
        "rendered_meaning.jsonl",
        "gold.jsonl",
        "semantic_candidates.jsonl",
        "semantic_attestations.jsonl",
        "execution_rows.jsonl",
        "graded_rows.jsonl",
        "compiler_fixture_results.jsonl",
        "frontier_dataset_manifest.json",
        "compiler_contract.json",
        "semantic_attestation_manifest.json",
        "baseline_manifest.json",
        "renderer_manifest.json",
        "claim_preregistration.json",
        "headroom_preflight.json",
        "leakage_report.json",
        "mutation_matrix.json",
        "source_inventory.json",
        "frontier_hashes.json",
    }
)
_SOURCE_FILES = (
    "app/eval/q5_frontier.py",
    "app/eval/q5_frontier_compiler_v3.py",
    "app/eval/q5_frontier_parser_suite_v3.py",
    "app/eval/q5_frontier_v3.py",
    "app/schemas/q5_frontier.py",
    "app/schemas/q5_frontier_v2.py",
    "app/schemas/q5_frontier_v3.py",
)
_ALL_DISPOSITIONS = list(FrontierDisposition)
_OBSERVATION = {
    FrontierResourceType.incident: FrontierObservationType.inspect_incident_state,
    FrontierResourceType.change: FrontierObservationType.inspect_change_state,
    FrontierResourceType.access: FrontierObservationType.inspect_access_scope,
    FrontierResourceType.retention: FrontierObservationType.inspect_retention_state,
}
_TRUE_DISPOSITION = {
    FrontierResourceType.incident: FrontierDisposition.remediate,
    FrontierResourceType.change: FrontierDisposition.notify,
    FrontierResourceType.access: FrontierDisposition.notify,
    FrontierResourceType.retention: FrontierDisposition.mark_stale,
}
_FACTS = {
    FrontierResourceType.incident: (FrontierPredicateField.status, "outage", "nominal"),
    FrontierResourceType.change: (
        FrontierPredicateField.temporal_state,
        "planned",
        "completed",
    ),
    FrontierResourceType.access: (FrontierPredicateField.scope, "restricted", "public"),
    FrontierResourceType.retention: (FrontierPredicateField.status, "expired", "current"),
}
_CLOSED_PATHS = frozenset(
    {
        "scope.resource_type",
        "scope.allowed_scopes",
        "temporal_state",
        "precedence",
        "evidence_requirements.observation_type",
        "terminal_safety.allowed_dispositions",
    }
)
_OPEN_PATHS = frozenset({"condition", "true_disposition", "false_disposition", "exceptions"})


@dataclass(frozen=True)
class _PairSpec:
    family: FrontierResourceType
    capability: str
    phenomenon: str
    pair_kind: str
    renderer_id: str
    distribution: str
    scenario: str
    gold: tuple[FrontierDisposition, FrontierDisposition]


def run_deterministic_parser_suite_v3(
    runtime_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Runtime-only execution; topology, Gold, IR, and authoring rows are absent."""

    runtimes = [FrontierRuntimePayloadV3.model_validate(row) for row in runtime_rows]
    refs = [item.runtime_ref for item in runtimes]
    if len(refs) != len(set(refs)):
        raise ValueError("runtime execution refs must be unique")
    rows: list[dict[str, Any]] = []
    for runtime in runtimes:
        status, reason, parsed_ir = deterministic_parser_suite_v3(runtime)
        terminal = FrontierDisposition.human_review
        if parsed_ir is not None:
            terminal = compile_policy_ir_v3(parsed_ir, runtime).disposition
        rows.append(
            FrontierExecutionRowV3(
                runtime_ref=runtime.runtime_ref,
                parser_status=status,
                parser_reason=reason,
                parser_suite="q5-deterministic-parser-suite-v3",
                terminal_disposition=terminal,
                parsed_ir_sha256=(
                    _hash_payload(parsed_ir.model_dump(mode="json")) if parsed_ir else None
                ),
            ).model_dump(mode="json")
        )
    return rows


def compile_and_grade_v3(
    *,
    execution_rows: Sequence[Mapping[str, Any]],
    runtime_rows: Sequence[Mapping[str, Any]],
    policy_ir_rows: Sequence[Mapping[str, Any]],
    topology_rows: Sequence[Mapping[str, Any]],
    gold_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Offline sealed join; semantic correctness is assigned only here."""

    runtime = _by_ref(runtime_rows, "runtime")
    ir_rows = _by_ref(policy_ir_rows, "Policy IR")
    topology = _by_ref(topology_rows, "topology")
    gold = _by_ref(gold_rows, "Gold")
    candidates = _by_ref(candidate_rows, "semantic candidates")
    refs = set(runtime)
    if not (refs == set(ir_rows) == set(topology) == set(gold)):
        raise ValueError("v3 offline grading matrix is incomplete")
    executions = [FrontierExecutionRowV3.model_validate(item) for item in execution_rows]
    if len(executions) != len(refs) or {item.runtime_ref for item in executions} != refs:
        raise ValueError("v3 execution trial matrix mismatch")
    attestations: list[dict[str, Any]] = []
    structural: dict[str, bool] = {}
    semantic: dict[str, bool] = {}
    for runtime_ref in sorted(refs):
        sealed_ir = CanonicalPolicyIR.model_validate(ir_rows[runtime_ref]["policy_ir"])
        expected = FrontierDisposition(gold[runtime_ref]["disposition"])
        compiled = compile_policy_ir_v3(
            sealed_ir, FrontierRuntimePayloadV3.model_validate(runtime[runtime_ref])
        )
        if compiled.disposition != expected:
            raise ValueError(f"hand-authored Gold disagrees with compiler: {runtime_ref}")
        candidate_row = candidates.get(runtime_ref)
        if candidate_row is None:
            structural[runtime_ref] = False
            semantic[runtime_ref] = False
            candidate_hash = "0" * 64
        else:
            candidate = FrontierSemanticCandidateV3.model_validate(candidate_row)
            structural[runtime_ref] = verify_semantic_candidate_structure(
                FrontierRuntimePayloadV3.model_validate(runtime[runtime_ref]), candidate
            )
            semantic[runtime_ref] = candidate.policy_ir == sealed_ir
            candidate_hash = _hash_payload(candidate.model_dump(mode="json"))
        attestations.append(
            FrontierAttestationV3(
                runtime_ref=runtime_ref,
                structural_integrity_verified=structural[runtime_ref],
                semantic_correctness_offline_graded=semantic[runtime_ref],
                semantic_correctness_source="sealed_ir_offline_grader",
                candidate_sha256=candidate_hash,
            ).model_dump(mode="json")
        )
    graded: list[dict[str, Any]] = []
    for execution in executions:
        item = topology[execution.runtime_ref]
        expected = FrontierDisposition(gold[execution.runtime_ref]["disposition"])
        unsafe = expected == FrontierDisposition.human_review and (
            execution.terminal_disposition != FrontierDisposition.human_review
        )
        graded.append(
            FrontierGradedRowV3(
                runtime_ref=execution.runtime_ref,
                capability_class=item["capability_class"],
                policy_family=item["policy_family"],
                semantic_phenomenon=item["semantic_phenomenon"],
                pair_id=item["pair_id"],
                pair_kind=item["pair_kind"],
                renderer_id=item["renderer_id"],
                renderer_distribution=item["renderer_distribution"],
                parser_status=execution.parser_status,
                terminal_disposition=execution.terminal_disposition,
                gold_disposition=expected,
                success=execution.terminal_disposition == expected,
                unsafe_terminal=unsafe,
                structural_integrity_verified=structural[execution.runtime_ref],
                semantic_correctness_offline_graded=semantic[execution.runtime_ref],
            ).model_dump(mode="json")
        )
    return graded, attestations


def verify_semantic_candidate_structure(
    runtime: FrontierRuntimePayloadV3,
    candidate: FrontierSemanticCandidateV3,
) -> bool:
    """Verify provenance and closed bindings, never open-language semantics."""

    if candidate.runtime_ref != runtime.runtime_ref:
        raise ValueError("semantic candidate crosses trial boundary")
    closed = {item.field_path: item for item in candidate.closed_bindings}
    opened = {item.field_path: item for item in candidate.open_provenance}
    if set(closed) != _CLOSED_PATHS or set(opened) != _OPEN_PATHS:
        raise ValueError("semantic candidate field closure mismatch")
    authorized = set(runtime.trusted_observation.authorization.authorized_evidence_ids)
    if not runtime.trusted_observation.authorization.authorized:
        raise ValueError("unauthorized runtime cannot attest semantic provenance")
    for item in [*candidate.closed_bindings, *candidate.open_provenance]:
        for span in item.policy_spans:
            if (
                span.end > len(runtime.policy_text)
                or runtime.policy_text[span.start : span.end] != span.text
            ):
                raise ValueError("semantic candidate span is foreign or stale")
    for item in candidate.open_provenance:
        if not set(item.authorized_evidence_ids) <= authorized:
            raise ValueError("semantic candidate uses unauthorized evidence")
    expected = _closed_values(candidate.policy_ir)
    if runtime.policy_text.startswith("Q5POLICYv5;"):
        parsed = structured_grammar_parser(runtime.policy_text)
        if parsed.status != "complete" or parsed.parsed_ir != candidate.policy_ir:
            raise ValueError("formal grammar binding mismatch")
        exact = expected
    else:
        exact = parse_closed_bindings_v3(runtime.policy_text)
    if exact != expected:
        raise ValueError("closed-vocabulary binding mismatch")
    for path, item in closed.items():
        if item.canonical_values != expected[path]:
            raise ValueError("closed binding canonical value mismatch")
        joined = " ".join(span.text for span in item.policy_spans)
        cited_values = (
            [_DISPOSITION_CODES[FrontierDisposition(value)] for value in expected[path]]
            if path == "terminal_safety.allowed_dispositions"
            and not runtime.policy_text.startswith("Q5POLICYv5;")
            else expected[path]
        )
        if any(value not in joined for value in cited_values):
            raise ValueError("closed binding value omitted from cited span")
    return True


def build_frontier_v3_artifacts(
    *,
    compiler_fixture_path: Path | str = Path("tests/fixtures/q5_frontier_v3/compiler_gold.json"),
) -> dict[str, bytes]:
    authored = _author_v3_rows()
    execution = run_deterministic_parser_suite_v3(authored["runtime_cases"])
    graded, attestations = compile_and_grade_v3(
        execution_rows=execution,
        runtime_rows=authored["runtime_cases"],
        policy_ir_rows=authored["policy_ir"],
        topology_rows=authored["topology"],
        gold_rows=authored["gold"],
        candidate_rows=authored["semantic_candidates"],
    )
    fixture_results = verify_compiler_gold_fixtures(compiler_fixture_path)
    pair_audit = validate_v3_pairs(authored)
    raw: dict[str, bytes] = {
        "policy_ir.jsonl": _jsonl_bytes(authored["policy_ir"]),
        "environment_authoring.jsonl": _jsonl_bytes(authored["environment_authoring"]),
        "runtime_cases.jsonl": _jsonl_bytes(authored["runtime_cases"]),
        "topology.jsonl": _jsonl_bytes(authored["topology"]),
        "rendered_meaning.jsonl": _jsonl_bytes(authored["rendered_meaning"]),
        "gold.jsonl": _jsonl_bytes(authored["gold"]),
        "semantic_candidates.jsonl": _jsonl_bytes(authored["semantic_candidates"]),
        "semantic_attestations.jsonl": _jsonl_bytes(attestations),
        "execution_rows.jsonl": _jsonl_bytes(execution),
        "graded_rows.jsonl": _jsonl_bytes(graded),
        "compiler_fixture_results.jsonl": _jsonl_bytes(fixture_results),
    }
    source_inventory = _source_inventory()
    dataset_manifest = _dataset_manifest(authored, raw, pair_audit)
    baseline = _baseline_manifest(graded)
    renderer = _renderer_manifest(authored)
    prereg = _claim_preregistration()
    headroom = maximum_possible_claim_headroom(graded, prereg)
    if not headroom["valid"]:
        raise ValueError("v3 preflight blocked by claim_headroom")
    attestation_manifest = _attestation_manifest(attestations, graded)
    compiler_contract = _compiler_contract(fixture_results)
    leakage = _leakage_report(authored, renderer)
    mutation = _mutation_matrix()
    raw.update(
        {
            "frontier_dataset_manifest.json": _json_bytes(dataset_manifest),
            "compiler_contract.json": _json_bytes(compiler_contract),
            "semantic_attestation_manifest.json": _json_bytes(attestation_manifest),
            "baseline_manifest.json": _json_bytes(baseline),
            "renderer_manifest.json": _json_bytes(renderer),
            "claim_preregistration.json": _json_bytes(prereg),
            "headroom_preflight.json": _json_bytes(headroom),
            "leakage_report.json": _json_bytes(leakage),
            "mutation_matrix.json": _json_bytes(mutation),
            "source_inventory.json": _json_bytes(source_inventory),
        }
    )
    raw["frontier_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-frontier-v6-hashes-v3",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    if set(raw) != FRONTIER_V3_FILES:
        raise ValueError("v3 artifact closure mismatch")
    return raw


def write_frontier_v3_artifacts(output_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"frontier v3 output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_frontier_v3_artifacts(**kwargs)
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["frontier_dataset_manifest.json"])


def verify_frontier_v3_artifacts(output_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
    target = Path(output_dir)
    actual = {item.name for item in target.iterdir() if item.is_file()}
    if actual != FRONTIER_V3_FILES:
        raise ValueError("v3 artifact closure mismatch")
    expected = build_frontier_v3_artifacts(**kwargs)
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"v3 recomputation mismatch: {name}")
    return json.loads(expected["frontier_dataset_manifest.json"])


def maximum_possible_claim_headroom(
    graded_rows: Sequence[Mapping[str, Any]],
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    semantic = [item for item in graded_rows if item["capability_class"] == "semantic_open"]
    abstained = [
        item
        for item in semantic
        if item["parser_status"] == "abstain" and item["semantic_correctness_offline_graded"]
    ]
    executed = [item for item in graded_rows if item["parser_status"] == "complete"]
    wrong = sum(not item["success"] for item in executed)
    risk = _ratio(wrong, len(executed)) if executed else None
    families = sorted({item["policy_family"] for item in abstained})
    phenomena = sorted({item["semantic_phenomenon"] for item in abstained})
    thresholds = preregistration["headline_thresholds"]
    possible = {
        "beneficial_distinct_cases": len(abstained),
        "beneficial_policy_families": len(families),
        "beneficial_semantic_phenomena": len(phenomena),
        "beneficial_capture": 1.0 if abstained else None,
        "llm_uplift_on_abstained_subset": 1.0 if abstained else None,
        "harmful_exposure": 0,
        "hybrid_oracle_regret": 0.0,
        "call_avoidance": _ratio(len(graded_rows) - len(abstained), len(graded_rows)),
        "token_avoidance": _ratio(len(graded_rows) - len(abstained), len(graded_rows)),
        "family_success": 1.0,
        "counterfactual_pair_success": 1.0,
        "unsafe_action": 0,
        "invalid_transition": 0,
        "schema_failure": 0,
    }
    blockers: list[str] = []
    checks = {
        "resolvable_deterministic_abstentions": len(abstained) >= 8,
        "four_policy_families": len(families) == 4,
        "four_semantic_phenomena": len(phenomena) >= 4,
        "deterministic_parser_conditional_risk_zero": risk == 0.0,
        "beneficial_distinct_cases_reachable": len(abstained)
        >= thresholds["beneficial_distinct_case_min"],
        "beneficial_families_reachable": len(families)
        >= thresholds["beneficial_policy_family_min"],
        "beneficial_phenomena_reachable": len(phenomena)
        >= thresholds["beneficial_semantic_phenomenon_min"],
        "all_preregistered_thresholds_mathematically_reachable": _thresholds_reachable(
            possible, thresholds
        ),
    }
    if not all(checks.values()):
        blockers.append("claim_headroom")
    return {
        "schema_version": "q5-frontier-maximum-claim-headroom-v3",
        "evaluated_before_model_calls": True,
        "model_calls_at_evaluation": 0,
        "external_requests_at_evaluation": 0,
        "resolvable_deterministic_abstention_count": len(abstained),
        "policy_families": families,
        "semantic_phenomena": phenomena,
        "deterministic_parser_conditional_risk": risk,
        "maximum_possible_metrics": possible,
        "checks": checks,
        "blockers": blockers,
        "valid": not blockers,
    }


def verify_compiler_gold_fixtures(path: Path | str) -> list[dict[str, Any]]:
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = fixture["cases"]
    results: list[dict[str, Any]] = []
    for row in rows:
        ir_payload = json.loads(json.dumps(fixture["base_policy_ir"]))
        runtime_payload = json.loads(json.dumps(fixture["base_runtime_payload"]))
        for path_key, value in row.get("policy_updates", {}).items():
            _set_dotted(ir_payload, path_key, value)
        for path_key, value in row.get("runtime_updates", {}).items():
            _set_dotted(runtime_payload, path_key, value)
        ir = CanonicalPolicyIR.model_validate(ir_payload)
        runtime = FrontierRuntimePayloadV3.model_validate(runtime_payload)
        actual = compile_policy_ir_v3(ir, runtime).disposition
        expected = FrontierDisposition(row["expected_disposition"])
        if actual != expected:
            raise ValueError(f"compiler fixture failed: {row['fixture_id']}")
        results.append(
            {
                "fixture_id": row["fixture_id"],
                "construct": row["construct"],
                "polarity": row["polarity"],
                "expected_disposition": expected.value,
                "actual_disposition": actual.value,
                "passed": True,
            }
        )
    required = {
        "scope",
        "temporal",
        "observation_type",
        "observation_completion",
        "authorization",
        "exception",
        "precedence_base_only",
        "precedence_exception_overrides",
        "precedence_deny_overrides",
        "predicate_eq",
        "predicate_ne",
        "predicate_in",
        "condition_all_of",
        "condition_any_of",
        "ambiguity",
        "terminal_legality",
        "disposition_branch",
    }
    by_construct: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_construct[row["construct"]].add(row["polarity"])
    if not required <= set(by_construct) or any(
        not {"positive", "negative", "metamorphic"} <= by_construct[item] for item in required
    ):
        raise ValueError("compiler Gold fixtures lack construct/polarity closure")
    return results


def _author_v3_rows() -> dict[str, list[dict[str, Any]]]:
    outputs: dict[str, list[dict[str, Any]]] = {
        "policy_ir": [],
        "environment_authoring": [],
        "runtime_cases": [],
        "topology": [],
        "rendered_meaning": [],
        "gold": [],
        "semantic_candidates": [],
    }
    ordinal = 0
    for pair_number, spec in enumerate(_pair_specs(), start=1):
        pair_id = f"frontier-v3-pair-{pair_number:02d}"
        for member in range(2):
            ordinal += 1
            runtime_ref = f"frontier-v3-resource:r{ordinal:03d}"
            ir, observation = _author_policy_and_observation(spec, member, ordinal)
            policy_text, clauses = _render_policy(ir, spec, member)
            runtime = FrontierRuntimePayloadV3(
                runtime_ref=runtime_ref,
                policy_text=policy_text,
                query=(
                    "Apply the policy meaning to the host-attested observation and "
                    "return one legal governance disposition."
                ),
                legal_dispositions=_ALL_DISPOSITIONS,
                trusted_observation=observation,
            )
            outputs["policy_ir"].append(
                {"runtime_ref": runtime_ref, "policy_ir": ir.model_dump(mode="json")}
            )
            outputs["environment_authoring"].append(
                {"runtime_ref": runtime_ref, "runtime_payload": runtime.model_dump(mode="json")}
            )
            outputs["runtime_cases"].append(runtime.model_dump(mode="json"))
            outputs["topology"].append(
                {
                    "runtime_ref": runtime_ref,
                    "capability_class": spec.capability,
                    "policy_family": spec.family.value,
                    "semantic_phenomenon": spec.phenomenon,
                    "pair_id": pair_id,
                    "pair_kind": spec.pair_kind,
                    "renderer_id": spec.renderer_id,
                    "renderer_distribution": spec.distribution,
                }
            )
            outputs["rendered_meaning"].append(
                {
                    "runtime_ref": runtime_ref,
                    "renderer_id": spec.renderer_id,
                    "renderer_distribution": spec.distribution,
                    "clauses": clauses,
                    "policy_text_sha256": _sha(policy_text.encode()),
                }
            )
            outputs["gold"].append(
                {
                    "runtime_ref": runtime_ref,
                    "disposition": spec.gold[member].value,
                    "source": "hand_authored_pair_decision_table_v3",
                }
            )
            if observation.authorization.authorized and observation.success:
                outputs["semantic_candidates"].append(
                    _build_candidate(runtime, ir).model_dump(mode="json")
                )
    if ordinal != FRONTIER_V3_CASE_COUNT:
        raise ValueError("v3 authoring did not emit 64 cases")
    return outputs


def _pair_specs() -> list[_PairSpec]:
    specs: list[_PairSpec] = []
    families = list(FrontierResourceType)
    for family_index, family in enumerate(families):
        action = _TRUE_DISPOSITION[family]
        direction = [
            "policy_fixed_state_changed",
            "state_fixed_policy_changed",
        ] * 4
        safety_scenario = (
            "observation_failure"
            if family in {FrontierResourceType.change, FrontierResourceType.retention}
            else "authorization"
        )
        configurations = [
            (
                "symbolic_complete",
                "structured_eq",
                "frontier-v3-formal-eq",
                "preregistered",
                "default",
            ),
            (
                "symbolic_complete",
                "structured_in",
                "frontier-v3-formal-set",
                "preregistered",
                "in_set",
            ),
            ("semantic_open", "cross_sentence_reference", "frontier-v3-reference", None, "default"),
            ("semantic_open", "nested_exception", "frontier-v3-nested", None, "nested_exception"),
            ("semantic_open", "negation_scope", "frontier-v3-negated-scope", None, "negation"),
            (
                "semantic_open",
                "temporal_scope_obligation",
                "frontier-v3-temporal-deontic",
                None,
                "temporal",
            ),
            (
                "ambiguous_or_unsafe",
                (
                    "observation_failure"
                    if safety_scenario == "observation_failure"
                    else "authorization_denied"
                ),
                f"frontier-v3-safety-{safety_scenario}",
                "preregistered",
                safety_scenario,
            ),
            (
                "ambiguous_or_unsafe",
                "conflict_resolution",
                "frontier-v3-safety-conflict",
                "preregistered",
                "conflict",
            ),
        ]
        for index, (capability, phenomenon, renderer, distribution, scenario) in enumerate(
            configurations
        ):
            if distribution is None:
                # Every family contributes two held-out pairs, while the held-out
                # slice spans all four semantic phenomena across families.
                held_out = (index + family_index) % 2 == 0
                distribution = "held_out" if held_out else "preregistered"
                renderer = f"{renderer}-{'heldout' if held_out else 'preregistered'}"
            second = FrontierDisposition.no_action
            if scenario in {
                "nested_exception",
                "authorization",
                "observation_failure",
                "conflict",
            }:
                second = FrontierDisposition.human_review
            specs.append(
                _PairSpec(
                    family=family,
                    capability=capability,
                    phenomenon=phenomenon,
                    pair_kind=direction[index],
                    renderer_id=renderer,
                    distribution=distribution,
                    scenario=scenario,
                    gold=(action, second),
                )
            )
    if len(specs) != 32:
        raise ValueError("v3 requires 32 pair specs")
    return specs


def _author_policy_and_observation(
    spec: _PairSpec,
    member: int,
    ordinal: int,
) -> tuple[CanonicalPolicyIR, FrontierTrustedObservation]:
    field, true_value, false_value = _FACTS[spec.family]
    operator = FrontierPredicateOperator.eq
    predicate_value: str | list[str] = true_value
    if spec.scenario == "in_set":
        operator = FrontierPredicateOperator.in_set
        predicate_value = [true_value, "production"]
    elif spec.scenario == "negation":
        field = FrontierPredicateField.status
        operator = FrontierPredicateOperator.ne
        true_value, false_value = "blocked", "nominal"
        predicate_value = true_value
    elif spec.scenario == "temporal":
        field = FrontierPredicateField.status
        true_value, false_value = "nominal", "blocked"
        predicate_value = true_value
    if spec.pair_kind == "state_fixed_policy_changed" and member == 1:
        if spec.scenario == "nested_exception":
            pass
        elif spec.scenario == "temporal":
            pass
        elif spec.scenario == "conflict":
            pass
        elif isinstance(predicate_value, list):
            predicate_value = [false_value, "production"]
        else:
            predicate_value = false_value
    temporal = (
        FrontierTemporalState.planned
        if spec.family == FrontierResourceType.change or spec.scenario == "temporal"
        else FrontierTemporalState.current
    )
    if (
        spec.pair_kind == "state_fixed_policy_changed"
        and member == 1
        and spec.scenario == "temporal"
    ):
        temporal = FrontierTemporalState.completed
    precedence = FrontierPrecedence.base_only
    if spec.scenario in {"in_set", "negation"}:
        precedence = FrontierPrecedence.deny_overrides
    if spec.scenario == "nested_exception" and member == 1:
        precedence = FrontierPrecedence.exception_overrides
    ambiguity = FrontierAmbiguityConflict()
    if spec.scenario == "conflict" and member == 1:
        ambiguity = FrontierAmbiguityConflict(
            kind=FrontierAmbiguityKind.conflicting_clauses,
            conflict_count=2,
        )
    all_of = [FrontierPredicate(field=field, operator=operator, value=predicate_value)]
    any_of: list[FrontierPredicate] = []
    if spec.family == FrontierResourceType.access and spec.phenomenon == "cross_sentence_reference":
        any_of = [
            FrontierPredicate(
                field=FrontierPredicateField.status,
                operator=FrontierPredicateOperator.eq,
                value="outage",
            ),
            FrontierPredicate(
                field=FrontierPredicateField.exception_active,
                operator=FrontierPredicateOperator.eq,
                value=True,
            ),
        ]
    if spec.family == FrontierResourceType.retention and spec.phenomenon == "nested_exception":
        all_of.append(
            FrontierPredicate(
                field=FrontierPredicateField.scope,
                operator=FrontierPredicateOperator.eq,
                value="production",
            )
        )
    ir = CanonicalPolicyIR(
        scope=FrontierPolicyScope(
            resource_type=spec.family,
            allowed_scopes=["production", "restricted"],
        ),
        condition=FrontierConditionExpression(all_of=all_of, any_of=any_of),
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
        evidence_requirements=FrontierEvidenceRequirements(
            observation_type=_OBSERVATION[spec.family].value
        ),
        true_disposition=_TRUE_DISPOSITION[spec.family],
        false_disposition=FrontierDisposition.no_action,
        ambiguity=ambiguity,
        terminal_safety=FrontierTerminalSafetyConstraints(allowed_dispositions=_ALL_DISPOSITIONS),
    )
    state = {
        "status": "nominal",
        "scope": "production",
        "temporal_state": temporal.value,
        "exception_active": False,
    }
    if spec.scenario == "nested_exception":
        state["exception_active"] = True
    if spec.scenario == "temporal":
        state["temporal_state"] = FrontierTemporalState.planned.value
    if any_of:
        state["status"] = "outage"
    state_value: Any = true_value
    if spec.pair_kind == "policy_fixed_state_changed" and member == 1:
        state_value = false_value
    if spec.scenario == "negation":
        state_value = false_value if member == 0 else true_value
    if spec.scenario in {"authorization", "observation_failure", "conflict"}:
        state_value = true_value
    if field == FrontierPredicateField.temporal_state:
        state["temporal_state"] = state_value
    else:
        state[field.value] = state_value
    authorized = not (
        spec.scenario == "authorization"
        and spec.pair_kind == "policy_fixed_state_changed"
        and member == 1
    )
    failed = (
        spec.scenario == "observation_failure"
        and spec.pair_kind == "policy_fixed_state_changed"
        and member == 1
    )
    evidence_ids = [f"chunk:v3-c{ordinal:03d}"] if authorized and not failed else []
    observation = FrontierTrustedObservation(
        observation_type=_OBSERVATION[spec.family],
        status=(FrontierObservationStatus.error if failed else FrontierObservationStatus.ok),
        success=not failed,
        authorization=FrontierHostAuthorization(
            authorized=authorized,
            authorized_evidence_ids=evidence_ids,
        ),
        request_id=f"observation:v3-o{ordinal:03d}",
        state=(None if failed else FrontierObservedState(**state)),
    )
    return ir, observation


def _render_policy(
    ir: CanonicalPolicyIR,
    spec: _PairSpec,
    member: int,
) -> tuple[str, list[str]]:
    if spec.capability == "symbolic_complete":
        clauses = _structured_clauses(ir)
        return "Q5POLICYv5; " + "; ".join([*clauses, "COMMENT v3-neutral"]), clauses
    closed = [
        f"Resource kind: {ir.scope.resource_type.value}.",
        f"Permitted scopes exactly: {','.join(ir.scope.allowed_scopes)}.",
        f"Policy time: {ir.temporal_state.value}.",
        f"Evidence probe: {ir.evidence_requirements.observation_type}.",
        f"Precedence mode: {ir.precedence.value}.",
        "Terminal codes exactly: "
        + ",".join(_DISPOSITION_CODES[item] for item in ir.terminal_safety.allowed_dispositions)
        + ".",
    ]
    condition = _semantic_condition(ir, spec, member)
    exception = (
        "Exception rule: if exception_active equals true, "
        f"{_ALIASES[FrontierDisposition.human_review]}."
    )
    conflict = f"Conflict status: {ir.ambiguity.kind.value}."
    clauses = [*closed, condition, exception, conflict]
    return " ".join(clauses), clauses


def _semantic_condition(
    ir: CanonicalPolicyIR,
    spec: _PairSpec,
    member: int,
) -> str:
    predicate = ir.condition.all_of[0]
    value = predicate.value
    value_text = ",".join(value) if isinstance(value, list) else str(value)
    true_alias = _ALIASES[ir.true_disposition]
    false_alias = _ALIASES[ir.false_disposition]
    compositional_suffix = ""
    if len(ir.condition.all_of) > 1:
        second = ir.condition.all_of[1]
        compositional_suffix += f" together with {second.field.value} equal to {second.value}"
    if ir.condition.any_of:
        options = " or ".join(
            f"{item.field.value} equal to {str(item.value).lower()}" for item in ir.condition.any_of
        )
        compositional_suffix += f" and at least one of {options}"
    if spec.scenario == "conflict" and member == 1:
        # The ordinary condition remains present. Ambiguity is carried by the
        # independently changing conflict-status clause.
        pass
    prefix = {
        "authorization": "The authorization-sensitive clause states that ",
        "observation_failure": "The completion-sensitive clause states that ",
        "conflict": "The conflict-screened clause states that ",
    }.get(spec.scenario, "")
    if spec.distribution == "preregistered":
        if spec.scenario in {"temporal", "nested_exception"}:
            return prefix + (
                f"Once observed {predicate.field.value} {predicate.operator.value} "
                f"{value_text}, {true_alias} is obligatory; in every other situation, "
                f"{false_alias}."
            )
        operator_word = {
            FrontierPredicateOperator.eq: "equals",
            FrontierPredicateOperator.ne: "does not equal",
            FrontierPredicateOperator.in_set: "belongs to",
        }[predicate.operator]
        return prefix + (
            f"An eligible record is one whose {predicate.field.value} {operator_word} "
            f"{value_text}. That antecedent calls for {true_alias}; otherwise "
            f"{false_alias}."
        )
    if spec.phenomenon == "cross_sentence_reference":
        return (
            f"A record qualifies whenever its {predicate.field.value} corresponds to "
            f"{value_text}{compositional_suffix}. What was just described makes it "
            f"proper to {true_alias}; "
            f"without that fact, {false_alias}."
        )
    if spec.phenomenon == "nested_exception":
        return (
            f"Ordinarily, a {predicate.field.value} of {value_text} supports the course "
            f"to {true_alias}{compositional_suffix}, with {false_alias} as the "
            "alternative. Even where that "
            "rule applies, the separately stated exception takes priority only under "
            "its declared precedence."
        )
    if spec.phenomenon == "negation_scope":
        return (
            f"Inside the permitted scope, it is not the case that "
            f"{predicate.field.value} may be {value_text}; while that negated condition "
            f"holds, {true_alias}, or else {false_alias}."
        )
    return (
        f"After the applicable policy time has arrived, observing "
        f"{predicate.field.value} as {value_text} creates an obligation to {true_alias}. "
        f"Before the combined time-and-scope condition is satisfied, {false_alias}."
    )


def _closed_values(ir: CanonicalPolicyIR) -> dict[str, list[str]]:
    return {
        "scope.resource_type": [ir.scope.resource_type.value],
        "scope.allowed_scopes": list(ir.scope.allowed_scopes),
        "temporal_state": [ir.temporal_state.value],
        "precedence": [ir.precedence.value],
        "evidence_requirements.observation_type": [str(ir.evidence_requirements.observation_type)],
        "terminal_safety.allowed_dispositions": [
            item.value for item in ir.terminal_safety.allowed_dispositions
        ],
    }


def _build_candidate(
    runtime: FrontierRuntimePayloadV3,
    ir: CanonicalPolicyIR,
) -> FrontierSemanticCandidateV3:
    text = runtime.policy_text
    evidence = list(runtime.trusted_observation.authorization.authorized_evidence_ids)
    if text.startswith("Q5POLICYv5;"):
        # Formal grammar is exactly bound by the formal parser; its full text is
        # a valid source span for each canonical field.
        whole = _span(text, 0, len(text))
        closed_spans = {path: [whole] for path in _CLOSED_PATHS}
        open_spans = {path: [whole] for path in _OPEN_PATHS}
    else:
        closed_spans = {
            "scope.resource_type": [_sentence_span(text, "Resource kind:")],
            "scope.allowed_scopes": [_sentence_span(text, "Permitted scopes exactly:")],
            "temporal_state": [_sentence_span(text, "Policy time:")],
            "evidence_requirements.observation_type": [_sentence_span(text, "Evidence probe:")],
            "precedence": [_sentence_span(text, "Precedence mode:")],
            "terminal_safety.allowed_dispositions": [
                _sentence_span(text, "Terminal codes exactly:")
            ],
        }
        condition = _condition_spans(text)
        exception = _sentence_span(text, "Exception rule:")
        open_spans = {
            "condition": condition,
            "true_disposition": condition,
            "false_disposition": condition,
            "exceptions": [exception],
        }
    return FrontierSemanticCandidateV3(
        runtime_ref=runtime.runtime_ref,
        policy_ir=ir,
        closed_bindings=[
            FrontierClosedBindingV3(
                field_path=path,
                canonical_values=values,
                policy_spans=closed_spans[path],
            )
            for path, values in sorted(_closed_values(ir).items())
        ],
        open_provenance=[
            FrontierOpenFieldProvenanceV3(
                field_path=path,
                policy_spans=open_spans[path],
                authorized_evidence_ids=evidence,
            )
            for path in sorted(_OPEN_PATHS)
        ],
    )


def _condition_spans(text: str) -> list[FrontierClauseSpan]:
    starts = [
        text.find(prefix)
        for prefix in (
            "An eligible record",
            "Once observed",
            "A record qualifies",
            "Ordinarily,",
            "Inside the permitted scope",
            "After the applicable policy time",
        )
    ]
    start = min(item for item in starts if item >= 0)
    end = text.find(" Exception rule:", start)
    if end < 0:
        raise ValueError("semantic condition span is missing")
    return [_span(text, start, end)]


def _sentence_span(text: str, prefix: str) -> FrontierClauseSpan:
    start = text.find(prefix)
    if start < 0:
        raise ValueError(f"policy sentence missing: {prefix}")
    end = text.find(".", start)
    if end < 0:
        raise ValueError(f"policy sentence unterminated: {prefix}")
    return _span(text, start, end + 1)


def _span(text: str, start: int, end: int) -> FrontierClauseSpan:
    value = text[start:end]
    return FrontierClauseSpan(
        start=start,
        end=end,
        text=value,
        sha256=_sha(value.encode()),
    )


def validate_v3_pairs(authored: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    ir = _by_ref(authored["policy_ir"], "pair IR")
    runtime = _by_ref(authored["runtime_cases"], "pair runtime")
    topology = _by_ref(authored["topology"], "pair topology")
    meaning = _by_ref(authored["rendered_meaning"], "pair meaning")
    pairs: dict[str, list[str]] = defaultdict(list)
    for runtime_ref, row in topology.items():
        pairs[row["pair_id"]].append(runtime_ref)
    if len(pairs) != 32 or any(len(items) != 2 for items in pairs.values()):
        raise ValueError("v3 requires 32 complete counterfactual pairs")
    counts = Counter()
    for pair_id, refs in sorted(pairs.items()):
        left, right = sorted(refs)
        kind = topology[left]["pair_kind"]
        if topology[right]["pair_kind"] != kind:
            raise ValueError("pair kind mismatch")
        left_ir = _ir_projection(ir[left]["policy_ir"])
        right_ir = _ir_projection(ir[right]["policy_ir"])
        left_runtime = FrontierRuntimePayloadV3.model_validate(runtime[left])
        right_runtime = FrontierRuntimePayloadV3.model_validate(runtime[right])
        left_state = _state_projection(left_runtime.trusted_observation)
        right_state = _state_projection(right_runtime.trusted_observation)
        left_clauses = meaning[left]["clauses"]
        right_clauses = meaning[right]["clauses"]
        counts[kind] += 1
        if kind == "policy_fixed_state_changed":
            if left_ir != right_ir or left_runtime.policy_text != right_runtime.policy_text:
                raise ValueError(f"policy-fixed meaning changed: {pair_id}")
            if len(_leaf_differences(left_state, right_state)) != 1:
                raise ValueError(f"policy-fixed pair changed more than one state fact: {pair_id}")
        else:
            if left_state != right_state:
                raise ValueError(f"state-fixed semantic environment changed: {pair_id}")
            if len(_leaf_differences(left_ir, right_ir)) != 1:
                raise ValueError(f"state-fixed pair changed more than one IR construct: {pair_id}")
            changed_clauses = sum(a != b for a, b in zip(left_clauses, right_clauses, strict=True))
            if len(left_clauses) != len(right_clauses) or changed_clauses != 1:
                raise ValueError(f"state-fixed pair changed more than one policy clause: {pair_id}")
    if counts != {
        "policy_fixed_state_changed": 16,
        "state_fixed_policy_changed": 16,
    }:
        raise ValueError("v3 pair directions are imbalanced")
    return {
        "pair_count": 32,
        "pair_kind_counts": dict(sorted(counts.items())),
        "canonical_ir_and_rendered_meaning_invariants": True,
        "single_variable_state_and_policy_invariants": True,
    }


def _ir_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(payload))
    # Pydantic-correlated ambiguity kind/count is one semantic construct.
    ambiguity = value.pop("ambiguity")
    value["ambiguity_construct"] = (ambiguity["kind"], ambiguity["conflict_count"])
    return value


def _state_projection(observation: FrontierTrustedObservation) -> dict[str, Any]:
    return {
        "authorized": observation.authorization.authorized,
        "completed_observation": (
            observation.state.model_dump(mode="json") if observation.success else None
        ),
        "observation_type": observation.observation_type.value,
    }


def _leaf_differences(left: Any, right: Any, path: str = "") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, Mapping):
        output: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                output.append(child)
            else:
                output.extend(_leaf_differences(left[key], right[key], child))
        return output
    if isinstance(left, list):
        if len(left) != len(right):
            return [path]
        output = []
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            output.extend(_leaf_differences(a, b, f"{path}[{index}]"))
        return output
    return [] if left == right else [path]


def _dataset_manifest(
    authored: Mapping[str, Sequence[Mapping[str, Any]]],
    raw: Mapping[str, bytes],
    pair_audit: Mapping[str, Any],
) -> dict[str, Any]:
    topology = authored["topology"]
    return {
        "schema_version": "q5-frontier-v6-dataset-manifest-v3",
        "protocol_namespace": "q5-frontier-v6-k0s",
        "namespace": "data/q5_frontier/dev-v3",
        "partition": "dev",
        "case_count": len(authored["runtime_cases"]),
        "capability_class_counts": dict(
            sorted(Counter(item["capability_class"] for item in topology).items())
        ),
        "policy_family_counts": dict(
            sorted(Counter(item["policy_family"] for item in topology).items())
        ),
        "renderer_distribution_counts": dict(
            sorted(Counter(item["renderer_distribution"] for item in topology).items())
        ),
        "pair_audit": pair_audit,
        "ir_coverage_matrix": _ir_coverage_matrix(authored),
        "execution_boundary": {
            "input_artifacts": ["runtime_cases.jsonl"],
            "forbidden_execution_inputs": [
                "policy_ir.jsonl",
                "environment_authoring.jsonl",
                "gold.jsonl",
                "topology.jsonl",
                "semantic_candidates.jsonl",
            ],
            "label_free": True,
        },
        "row_sha256": {name: _sha(payload) for name, payload in sorted(raw.items())},
    }


def _ir_coverage_matrix(
    authored: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    irs = [CanonicalPolicyIR.model_validate(item["policy_ir"]) for item in authored["policy_ir"]]
    runtimes = [FrontierRuntimePayloadV3.model_validate(item) for item in authored["runtime_cases"]]
    operators = Counter(
        predicate.operator.value
        for ir in irs
        for predicate in [*ir.condition.all_of, *ir.condition.any_of]
    )
    precedence = Counter(ir.precedence.value for ir in irs)
    states = [runtime.trusted_observation.state for runtime in runtimes]
    return {
        "predicate_operator_counts": dict(sorted(operators.items())),
        "all_of_case_count": sum(bool(ir.condition.all_of) for ir in irs),
        "any_of_case_count": sum(bool(ir.condition.any_of) for ir in irs),
        "precedence_counts": dict(sorted(precedence.items())),
        "exception_active_count": sum(bool(state and state.exception_active) for state in states),
        "exception_inactive_count": sum(
            bool(state and not state.exception_active) for state in states
        ),
        "scope_match_count": sum(
            bool(
                runtime.trusted_observation.state
                and runtime.trusted_observation.state.scope in ir.scope.allowed_scopes
            )
            for runtime, ir in zip(runtimes, irs, strict=True)
        ),
        "scope_mismatch_count": sum(
            bool(
                runtime.trusted_observation.state
                and runtime.trusted_observation.state.scope not in ir.scope.allowed_scopes
            )
            for runtime, ir in zip(runtimes, irs, strict=True)
        ),
        "temporal_match_count": sum(
            bool(
                runtime.trusted_observation.state
                and runtime.trusted_observation.state.temporal_state == ir.temporal_state.value
            )
            for runtime, ir in zip(runtimes, irs, strict=True)
        ),
        "temporal_mismatch_count": sum(
            bool(
                runtime.trusted_observation.state
                and runtime.trusted_observation.state.temporal_state != ir.temporal_state.value
            )
            for runtime, ir in zip(runtimes, irs, strict=True)
        ),
        "authorized_count": sum(
            runtime.trusted_observation.authorization.authorized for runtime in runtimes
        ),
        "unauthorized_count": sum(
            not runtime.trusted_observation.authorization.authorized for runtime in runtimes
        ),
        "observation_failure_count": sum(
            not runtime.trusted_observation.success for runtime in runtimes
        ),
        "observation_type_families": sorted(
            {runtime.trusted_observation.observation_type.value for runtime in runtimes}
        ),
    }


def _baseline_manifest(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    completed = [item for item in rows if item["parser_status"] == "complete"]
    semantic = [item for item in rows if item["capability_class"] == "semantic_open"]
    heldout = [item for item in semantic if item["renderer_distribution"] == "held_out"]
    wrong = sum(not item["success"] for item in completed)
    return {
        "schema_version": "q5-frontier-v6-baseline-manifest-v3",
        "parser_suite": "q5-deterministic-parser-suite-v3",
        "parser_suite_preregistered": True,
        "parser_suite_source_sha256": _sha(
            _project_path("app/eval/q5_frontier_parser_suite_v3.py").read_bytes()
        ),
        "case_count": len(rows),
        "parser_complete_count": len(completed),
        "parser_conditional_risk": _ratio(wrong, len(completed)),
        "semantic_open_case_count": len(semantic),
        "semantic_open_complete_count": sum(
            item["parser_status"] == "complete" for item in semantic
        ),
        "held_out_semantic_abstention_count": sum(
            item["parser_status"] == "abstain" for item in heldout
        ),
        "unsafe_terminal_count": sum(item["unsafe_terminal"] for item in rows),
        "llm_calls": 0,
        "external_requests": 0,
        "claim_scope": (
            "incremental LLM value for some open semantic parsing under the "
            "preregistered deterministic parser suite and subsequent held-out "
            "renderer distribution"
        ),
        "parser_impossibility_claim_forbidden": True,
    }


def _renderer_manifest(
    authored: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    topology = authored["topology"]
    runtime = authored["runtime_cases"]
    ids = sorted({item["renderer_id"] for item in topology})
    multiplicity = Counter(item["policy_text"] for item in runtime)
    return {
        "schema_version": "q5-frontier-v6-renderer-manifest-v3",
        "parser_suite_frozen_source_sha256": _sha(
            _project_path("app/eval/q5_frontier_parser_suite_v3.py").read_bytes()
        ),
        "held_out_renderer_authoring_source_sha256": _sha(
            _project_path("app/eval/q5_frontier_v3.py").read_bytes()
        ),
        "parser_suite_and_renderer_authoring_source_separated": True,
        "renderer_family_count": len(ids),
        "renderer_ids": ids,
        "preregistered_renderer_ids": sorted(
            {
                item["renderer_id"]
                for item in topology
                if item["renderer_distribution"] == "preregistered"
            }
        ),
        "held_out_renderer_ids": sorted(
            {
                item["renderer_id"]
                for item in topology
                if item["renderer_distribution"] == "held_out"
            }
        ),
        "unique_policy_text_count": len(multiplicity),
        "policy_text_multiplicity": dict(sorted(Counter(multiplicity.values()).items())),
        "semantic_open_uses_canonical_action_wording": any(
            re.search(
                r"\b(mark_stale|remediate|notify|human_review|no_action)\b", item["policy_text"]
            )
            for item, top in zip(runtime, topology, strict=True)
            if top["capability_class"] == "semantic_open"
        ),
        "test_distribution": {"status": "not_evaluated", "reason": "q5_test absent"},
    }


def _claim_preregistration() -> dict[str, Any]:
    return {
        "schema_version": "q5-frontier-v6-claim-preregistration-v3",
        "claim": (
            "Under the preregistered deterministic parser suite and subsequent "
            "held-out renderer distribution, an LLM provides incremental value for "
            "a subset of open semantic parsing."
        ),
        "claim_status": "preregistered_not_yet_evaluated",
        "forbidden_claim": "no deterministic parser can solve the policies",
        "headline_thresholds": {
            "llm_uplift_on_parser_abstained_subset_min": 0.10,
            "parser_conditional_risk_max": 0.0,
            "beneficial_distinct_case_min": 8,
            "beneficial_policy_family_min": 4,
            "beneficial_semantic_phenomenon_min": 4,
            "beneficial_capture_min": 0.75,
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
        "model_calls_before_headroom_preflight_forbidden": True,
    }


def _thresholds_reachable(possible: Mapping[str, Any], thresholds: Mapping[str, Any]) -> bool:
    mapping = {
        "llm_uplift_on_parser_abstained_subset_min": "llm_uplift_on_abstained_subset",
        "beneficial_distinct_case_min": "beneficial_distinct_cases",
        "beneficial_policy_family_min": "beneficial_policy_families",
        "beneficial_semantic_phenomenon_min": "beneficial_semantic_phenomena",
        "beneficial_capture_min": "beneficial_capture",
        "call_avoidance_min": "call_avoidance",
        "token_avoidance_min": "token_avoidance",
        "family_success_min": "family_success",
        "counterfactual_pair_success_min": "counterfactual_pair_success",
    }
    for threshold, metric in mapping.items():
        if possible[metric] is None or possible[metric] < thresholds[threshold]:
            return False
    maxima = {
        "harmful_exposure_max": "harmful_exposure",
        "hybrid_oracle_regret_max": "hybrid_oracle_regret",
        "unsafe_action_max": "unsafe_action",
        "invalid_transition_max": "invalid_transition",
        "schema_failure_max": "schema_failure",
    }
    return all(possible[metric] <= thresholds[threshold] for threshold, metric in maxima.items())


def _attestation_manifest(
    attestations: Sequence[Mapping[str, Any]],
    graded: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "q5-frontier-semantic-attestation-manifest-v3",
        "structural_integrity_verified_count": sum(
            item["structural_integrity_verified"] for item in attestations
        ),
        "semantic_correctness_offline_graded_count": sum(
            item["semantic_correctness_offline_graded"] for item in attestations
        ),
        "semantic_correctness_is_runtime_attestation": False,
        "closed_vocabulary_exact_binding": True,
        "open_language_provenance_claim": "source_and_completeness_only",
        "open_language_semantics_source": "sealed_ir_offline_grader",
        "graded_row_count": len(graded),
    }


def _compiler_contract(fixtures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    constructs = Counter(item["construct"] for item in fixtures)
    return {
        "schema_version": "q5-frontier-policy-ir-compiler-contract-v3",
        "compiler": "compile_policy_ir_v3",
        "semantics": {
            "scope": "observed scope must be in allowed_scopes; otherwise false branch",
            "temporal": (
                "observed temporal state must equal policy temporal state; otherwise false branch"
            ),
            "observation_type": "exact match required; mismatch is human_review",
            "authorization": (
                "host authorization plus nonempty evidence required; failure is human_review"
            ),
            "observation_completion": (
                "successful typed observation required; failure is human_review"
            ),
            "ambiguity": "non-none ambiguity is human_review",
            "base_only": "ignore matching exception and execute the base branch",
            "exception_overrides": (
                "unique matching exception replaces base; conflict is human_review"
            ),
            "deny_overrides": "human_review then no_action dominate; otherwise preserve base",
        },
        "gold_fixture_source": "independent_handwritten_json",
        "compiler_generated_expected_results": False,
        "fixture_count": len(fixtures),
        "construct_counts": dict(sorted(constructs.items())),
        "all_passed": all(item["passed"] for item in fixtures),
    }


def _leakage_report(
    authored: Mapping[str, Sequence[Mapping[str, Any]]],
    renderer: Mapping[str, Any],
) -> dict[str, Any]:
    runtime = authored["runtime_cases"]
    runtime_keys = _recursive_keys(runtime)
    forbidden = {
        "policy_ir",
        "gold",
        "topology",
        "capability_class",
        "policy_family",
        "semantic_phenomenon",
        "pair_id",
        "pair_kind",
        "renderer_id",
        "renderer_distribution",
        "expected_action",
        "expected_disposition",
    }
    source = inspect.getsource(run_deterministic_parser_suite_v3)
    checks = {
        "sealed_fields_absent_from_runtime": not (runtime_keys & forbidden),
        "execution_signature_runtime_only": list(
            inspect.signature(run_deterministic_parser_suite_v3).parameters
        )
        == ["runtime_rows"],
        "execution_source_has_no_sealed_join": all(
            token not in source
            for token in ("gold_rows", "topology_rows", "policy_ir_rows", "candidate_rows")
        ),
        "semantic_open_canonical_action_wording_absent": not renderer[
            "semantic_open_uses_canonical_action_wording"
        ],
        "q5_test_absent": not (Path(__file__).resolve().parents[2] / "data/q5_test").exists(),
        "external_requests": 0,
        "model_calls": 0,
    }
    return {
        "schema_version": "q5-frontier-v6-leakage-report-v3",
        "valid": all(value is True or value == 0 for value in checks.values()),
        "checks": checks,
        "leaked_runtime_keys": sorted(runtime_keys & forbidden),
        "action_label_exposure": {
            "semantic_open_canonical_tokens": [],
            "formal_and_terminal_ontology_expected": True,
        },
        "unique_text_template_multiplicity": {
            "unique_policy_text_count": renderer["unique_policy_text_count"],
            "multiplicity": renderer["policy_text_multiplicity"],
        },
        "renderer_coverage": dict(
            sorted(Counter(item["renderer_id"] for item in authored["topology"]).items())
        ),
        "dev_test_disjointness": {
            "status": "not_evaluated",
            "passed": None,
            "reason": "q5_test does not exist",
        },
    }


def _mutation_matrix() -> dict[str, Any]:
    mutations = {
        "semantic_attestation": [
            "true_false_disposition_swap",
            "predicate_operator_swap",
            "exception_predicate_swap",
            "exception_disposition_swap",
            "scope_binding_omission",
            "observation_type_swap",
            "cross_trial_policy_span",
            "unauthorized_evidence",
            "semantic_correctness_self_attestation",
        ],
        "compiler": [
            "scope_guard_bypass",
            "temporal_guard_bypass",
            "observation_type_guard_bypass",
            "authorization_guard_bypass",
            "base_only_semantics_swap",
            "exception_override_semantics_swap",
            "deny_override_semantics_swap",
        ],
        "pairs": [
            "synchronized_policy_fixed_state_mutation",
            "synchronized_state_fixed_policy_mutation",
        ],
        "headroom": [
            "abstention_count_inflation",
            "family_coverage_inflation",
            "phenomenon_coverage_inflation",
            "conditional_risk_suppression",
            "claim_headroom_blocker_deletion",
        ],
        "artifact_closure": [
            "missing_artifact",
            "extra_artifact",
            "source_inventory_forgery",
            "graded_row_rewrite",
        ],
    }
    return {
        "schema_version": "q5-frontier-v6-mutation-matrix-v3",
        "mutation_count": sum(len(items) for items in mutations.values()),
        "expected_result": "fail_closed",
        "mutations": mutations,
        "external_requests": 0,
    }


def _source_inventory() -> dict[str, Any]:
    hashes = {name: _sha(_project_path(name).read_bytes()) for name in _SOURCE_FILES}
    fixture = Path("tests/fixtures/q5_frontier_v3/compiler_gold.json")
    hashes[fixture.as_posix()] = _sha(fixture.read_bytes())
    return {
        "schema_version": "q5-frontier-v6-source-inventory-v3",
        "files": hashes,
        "inventory_sha256": _hash_payload(hashes),
    }


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return set(value) | set().union(*(_recursive_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_recursive_keys(item) for item in value), set())
    return set()


def _by_ref(rows: Sequence[Mapping[str, Any]], label: str) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        runtime_ref = row.get("runtime_ref")
        if not isinstance(runtime_ref, str) or runtime_ref in output:
            raise ValueError(f"{label} refs are missing or duplicated")
        output[runtime_ref] = row
    return output


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _set_dotted(payload: Any, path: str, value: Any) -> None:
    current = payload
    parts = path.split(".")
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = value
    else:
        current[last] = value


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode()


def _hash_payload(payload: Any) -> str:
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _project_path(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / name
