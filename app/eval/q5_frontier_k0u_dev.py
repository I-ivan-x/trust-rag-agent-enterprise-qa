"""K0U-C handwritten development frontier and offline grading boundary."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.eval.q5_frontier import _structured_clauses, structured_grammar_parser
from app.eval.q5_frontier_compiler_v4 import compile_policy_ir_v4
from app.eval.q5_frontier_k0u_handwritten import HANDWRITTEN_PAIRS
from app.eval.q5_frontier_k0u_prereg import FROZEN_K0U_SOURCES
from app.eval.q5_frontier_k0u_prereg_parser import preregistered_practical_parser
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
    FrontierHostAuthorization,
    FrontierObservationStatus,
    FrontierObservationType,
    FrontierObservedState,
    FrontierTrustedObservation,
)
from app.schemas.q5_frontier_v4 import FrontierRuntimePayloadV4
from app.schemas.q5_frontier_v6 import PracticalObservationInput, PracticalRuntimeInput

K0U_PREREG_COMMIT = "b11c97c52d95075b177baee42c0466f6639761fb"
K0U_DEV_FILES = frozenset(
    {
        "runtime_cases.jsonl",
        "policy_ir.jsonl",
        "environment_authoring.jsonl",
        "topology.jsonl",
        "gold.jsonl",
        "execution_rows.jsonl",
        "graded_rows.jsonl",
        "policy_inventory.jsonl",
        "coverage_report.json",
        "metric_report.json",
        "dataset_manifest.json",
        "prereg_receipt.json",
        "artifact_hashes.json",
    }
)
FAMILIES = tuple(FrontierResourceType)
SEMANTIC_ACTIONS = (
    FrontierDisposition.mark_stale,
    FrontierDisposition.remediate,
    FrontierDisposition.notify,
    FrontierDisposition.no_action,
)
OBSERVATION_BY_FAMILY = {
    FrontierResourceType.incident: FrontierObservationType.inspect_incident_state,
    FrontierResourceType.change: FrontierObservationType.inspect_change_state,
    FrontierResourceType.access: FrontierObservationType.inspect_access_scope,
    FrontierResourceType.retention: FrontierObservationType.inspect_retention_state,
}


def build_k0u_dev_artifacts() -> dict[str, bytes]:
    authored = _author_rows()
    gold = _offline_gold(authored["runtime"], authored["policy_ir"])
    execution = _execute(authored["runtime"])
    graded = _grade(execution, authored["topology"], gold)
    inventory = _policy_inventory(authored["topology"], authored["runtime"])
    coverage = _coverage(authored, gold, inventory)
    metrics = _metrics(graded)
    _enforce(coverage, metrics)
    manifest = {
        "schema_version": "q5-k0u-dev-manifest-v1",
        "partition": "parser_uncovered_dev",
        "case_count": 96,
        "capability_counts": coverage["capability_counts"],
        "semantic_coverage_counts": coverage["semantic_coverage_counts"],
        "prereg_commit": K0U_PREREG_COMMIT,
        "external_requests": 0,
        "model_requests": 0,
    }
    raw = {
        "runtime_cases.jsonl": _jsonl_bytes(authored["runtime"]),
        "policy_ir.jsonl": _jsonl_bytes(authored["policy_ir"]),
        "environment_authoring.jsonl": _jsonl_bytes(authored["environment"]),
        "topology.jsonl": _jsonl_bytes(authored["topology"]),
        "gold.jsonl": _jsonl_bytes(gold),
        "execution_rows.jsonl": _jsonl_bytes(execution),
        "graded_rows.jsonl": _jsonl_bytes(graded),
        "policy_inventory.jsonl": _jsonl_bytes(inventory),
        "coverage_report.json": _json_bytes(coverage),
        "metric_report.json": _json_bytes(metrics),
        "dataset_manifest.json": _json_bytes(manifest),
        "prereg_receipt.json": _json_bytes(_prereg_receipt()),
    }
    raw["artifact_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-k0u-dev-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_k0u_dev(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"K0U dev output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_k0u_dev_artifacts()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["dataset_manifest.json"])


def verify_k0u_dev(
    output_dir: Path | str,
    *,
    require_parent_commit: bool = False,
) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != K0U_DEV_FILES:
        raise ValueError("K0U dev artifact closure mismatch")
    expected = build_k0u_dev_artifacts()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"K0U dev recomputation mismatch: {name}")
    if require_parent_commit:
        receipt = json.loads(expected["prereg_receipt.json"])
        if _git("rev-parse", "HEAD^") != K0U_PREREG_COMMIT:
            raise ValueError("K0U-C parent is not K0U-B")
        for path, identity in receipt["frozen_sources"].items():
            if _git("rev-parse", f"HEAD:{path}") != identity["git_blob_sha"]:
                raise ValueError(f"K0U-C changed frozen parser source: {path}")
    return json.loads(expected["dataset_manifest.json"])


def _author_rows() -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counter = 0
    for family_index, family in enumerate(FAMILIES):
        for local in range(4):
            counter += 1
            value = f"signal_{counter:03d}"
            ir = _policy_ir(
                family,
                value,
                SEMANTIC_ACTIONS[(family_index + local) % 4],
                SEMANTIC_ACTIONS[(family_index + local + 1) % 4],
                "all",
            )
            _append(
                rows,
                counter,
                family,
                "symbolic_complete",
                "structured_policy",
                "symbolic",
                "none",
                "none",
                ir,
                value,
                "Q5POLICYv5; " + "; ".join(_structured_clauses(ir)),
            )
    for pair_index, spec in enumerate(HANDWRITTEN_PAIRS):
        family = FrontierResourceType(spec.family)
        family_index = FAMILIES.index(family)
        coverage_index = 0 if spec.coverage == "parser_covered" else 1
        base = 100 + pair_index * 3 if coverage_index == 0 else 300 + (pair_index - 16) * 3
        target = f"signal_{base:03d}"
        first_alt = f"neutral_{base + 1:03d}"
        action_offset = 2 * coverage_index
        true_action = SEMANTIC_ACTIONS[(family_index + action_offset) % 4]
        false_action = SEMANTIC_ACTIONS[(family_index + action_offset + 1) % 4]
        if spec.direction == "policy_fixed_state_changed":
            policy_values = (target, target)
            state_values = (target, first_alt)
        else:
            state_values = (target, target)
            policy_values = (target, first_alt)
        mode = "any" if spec.phenomenon == "multi_condition_any" else "all"
        for member, text in enumerate((spec.text_a, spec.text_b)):
            counter += 1
            ir = _policy_ir(
                family,
                policy_values[member],
                true_action,
                false_action,
                mode,
            )
            _append(
                rows,
                counter,
                family,
                "semantic_open",
                spec.phenomenon,
                spec.coverage,
                f"k0u-{spec.coverage}-pair-{pair_index:02d}",
                spec.direction,
                ir,
                state_values[member],
                text,
            )
    for family_index, family in enumerate(FAMILIES):
        for local in range(4):
            counter += 1
            value = f"signal_{600 + counter:03d}"
            ir = _policy_ir(
                family,
                value,
                SEMANTIC_ACTIONS[(family_index + local) % 4],
                SEMANTIC_ACTIONS[(family_index + local + 1) % 4],
                "all",
                ambiguous=True,
            )
            _append(
                rows,
                counter,
                family,
                "ambiguous_or_unsafe",
                "conflict_or_authorization",
                "unsafe",
                "none",
                "none",
                ir,
                value,
                "Conflict: irreconcilable.",
                authorized=local % 2 == 0,
                successful=local < 2,
            )
    if counter != 96 or len(HANDWRITTEN_PAIRS) != 32:
        raise AssertionError("K0U requires 96 cases and 32 handwritten semantic pairs")
    return rows


def _append(
    rows,
    counter,
    family,
    capability,
    phenomenon,
    coverage,
    pair_id,
    pair_kind,
    ir,
    status_value,
    policy_text,
    *,
    authorized=True,
    successful=True,
):
    runtime_ref = f"frontier-k0u-dev-resource:r{counter:03d}"
    observation = FrontierTrustedObservation(
        observation_type=OBSERVATION_BY_FAMILY[family],
        status=FrontierObservationStatus.ok if successful else FrontierObservationStatus.timeout,
        success=successful,
        authorization=FrontierHostAuthorization(
            authorized=authorized,
            authorized_evidence_ids=(
                [f"chunk:k0u-{counter:03d}"] if authorized and successful else []
            ),
        ),
        request_id=f"observation:k0u-{counter:03d}",
        state=(
            FrontierObservedState(
                status=status_value,
                scope="production",
                temporal_state="current",
                exception_active=False,
            )
            if successful
            else None
        ),
    )
    rows["runtime"].append(
        {
            "runtime_ref": runtime_ref,
            "policy_text": policy_text,
            "query": "Determine the governed disposition from the typed observation.",
            "legal_dispositions": [item.value for item in FrontierDisposition],
            "trusted_observation": observation.model_dump(mode="json"),
        }
    )
    rows["policy_ir"].append({"runtime_ref": runtime_ref, "policy_ir": ir.model_dump(mode="json")})
    rows["environment"].append(
        {"runtime_ref": runtime_ref, "trusted_observation": observation.model_dump(mode="json")}
    )
    rows["topology"].append(
        {
            "runtime_ref": runtime_ref,
            "capability_class": capability,
            "semantic_coverage": coverage,
            "policy_family": family.value,
            "semantic_phenomenon": phenomenon,
            "pair_id": pair_id,
            "pair_kind": pair_kind,
        }
    )


def _policy_ir(family, value, true_action, false_action, mode, *, ambiguous=False):
    status_predicate = FrontierPredicate(
        field=FrontierPredicateField.status,
        operator=FrontierPredicateOperator.eq,
        value=value,
    )
    scope_predicate = FrontierPredicate(
        field=FrontierPredicateField.scope,
        operator=FrontierPredicateOperator.eq,
        value="production",
    )
    condition = (
        FrontierConditionExpression(
            all_of=[scope_predicate],
            any_of=[
                status_predicate,
                FrontierPredicate(
                    field=FrontierPredicateField.temporal_state,
                    operator=FrontierPredicateOperator.eq,
                    value="completed",
                ),
            ],
        )
        if mode == "any"
        else FrontierConditionExpression(all_of=[status_predicate, scope_predicate])
    )
    return CanonicalPolicyIR(
        scope=FrontierPolicyScope(
            resource_type=family,
            allowed_scopes=["production", "restricted"],
        ),
        condition=condition,
        temporal_state=FrontierTemporalState.current,
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
        precedence=FrontierPrecedence.exception_overrides,
        evidence_requirements=FrontierEvidenceRequirements(
            observation_type=OBSERVATION_BY_FAMILY[family].value
        ),
        true_disposition=true_action,
        false_disposition=false_action,
        ambiguity=(
            FrontierAmbiguityConflict(
                kind=FrontierAmbiguityKind.conflicting_clauses, conflict_count=2
            )
            if ambiguous
            else FrontierAmbiguityConflict()
        ),
        terminal_safety=FrontierTerminalSafetyConstraints(
            allowed_dispositions=list(FrontierDisposition)
        ),
    )


def _practical(raw):
    observation = raw["trusted_observation"]
    state = observation["state"]
    return PracticalRuntimeInput(
        policy_text=raw["policy_text"],
        observation=PracticalObservationInput(
            status=state["status"] if state else "unavailable",
            scope=state["scope"] if state else "unavailable",
            temporal_state=state["temporal_state"] if state else "current",
            exception_active=state["exception_active"] if state else False,
            authorized=observation["authorization"]["authorized"],
            successful=observation["success"],
        ),
        legal_dispositions=raw["legal_dispositions"],
    )


def _offline_gold(runtime_rows, policy_rows):
    policies = {
        row["runtime_ref"]: CanonicalPolicyIR.model_validate(row["policy_ir"])
        for row in policy_rows
    }
    rows = []
    for raw in runtime_rows:
        observation = FrontierTrustedObservation.model_validate(raw["trusted_observation"])
        v4 = FrontierRuntimePayloadV4(
            runtime_ref=raw["runtime_ref"].replace(
                "frontier-k0u-dev-resource", "parser-uncovered-dev-resource"
            ),
            policy_text=raw["policy_text"],
            query=raw["query"],
            legal_dispositions=raw["legal_dispositions"],
            trusted_observation=observation,
        )
        result = compile_policy_ir_v4(policies[raw["runtime_ref"]], v4)
        rows.append({"runtime_ref": raw["runtime_ref"], "disposition": result.disposition.value})
    return rows


def _execute(runtime_rows):
    rows = []
    for raw in runtime_rows:
        if raw["policy_text"].startswith("Q5POLICYv5;"):
            parsed = structured_grammar_parser(raw["policy_text"])
            practical = _practical(raw)
            if parsed.status == "complete":
                # Structured cases are outside the semantic call accounting.
                observation = FrontierTrustedObservation.model_validate(raw["trusted_observation"])
                v4 = FrontierRuntimePayloadV4(
                    runtime_ref=raw["runtime_ref"].replace(
                        "frontier-k0u-dev-resource", "parser-uncovered-dev-resource"
                    ),
                    policy_text=raw["policy_text"],
                    query=raw["query"],
                    legal_dispositions=raw["legal_dispositions"],
                    trusted_observation=observation,
                )
                terminal = compile_policy_ir_v4(parsed.parsed_ir, v4).disposition.value
                status = "complete"
            else:
                terminal, status = "human_review", parsed.status
            del practical
        else:
            parsed = preregistered_practical_parser(_practical(raw))
            terminal = parsed.disposition.value if parsed.disposition else "human_review"
            status = parsed.status
        rows.append(
            {
                "runtime_ref": raw["runtime_ref"],
                "parser_status": status,
                "terminal_disposition": terminal,
                "external_requests": 0,
                "model_requests": 0,
            }
        )
    return rows


def _grade(execution, topology, gold):
    top = {row["runtime_ref"]: row for row in topology}
    labels = {row["runtime_ref"]: row["disposition"] for row in gold}
    return [
        {
            **top[row["runtime_ref"]],
            **row,
            "gold_disposition": labels[row["runtime_ref"]],
            "success": row["terminal_disposition"] == labels[row["runtime_ref"]],
            "unsafe_terminal": (
                top[row["runtime_ref"]]["capability_class"] == "ambiguous_or_unsafe"
                and row["terminal_disposition"] != "human_review"
            ),
        }
        for row in execution
    ]


def _policy_inventory(topology, runtime):
    top = {row["runtime_ref"]: row for row in topology}
    return [
        {
            "runtime_ref": row["runtime_ref"],
            "coverage": top[row["runtime_ref"]]["semantic_coverage"],
            "policy_text_sha256": _sha(row["policy_text"].encode()),
            "policy_text": row["policy_text"],
        }
        for row in runtime
        if top[row["runtime_ref"]]["capability_class"] == "semantic_open"
    ]


def _coverage(authored, gold, inventory):
    topology = authored["topology"]
    labels = {row["runtime_ref"]: row["disposition"] for row in gold}
    semantic = [row for row in topology if row["capability_class"] == "semantic_open"]
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in semantic:
        pairs[row["pair_id"]].append(row)
    if any(len(items) != 2 for items in pairs.values()):
        raise ValueError("K0U semantic pairs must be complete")
    by_slice = {
        coverage: dict(
            Counter(
                members[0]["pair_kind"]
                for members in pairs.values()
                if members[0]["semantic_coverage"] == coverage
            )
        )
        for coverage in ("parser_covered", "parser_uncovered")
    }
    family_actions = {
        family.value: sorted(
            {labels[row["runtime_ref"]] for row in semantic if row["policy_family"] == family.value}
        )
        for family in FAMILIES
    }
    family_action_counts = {
        family.value: dict(
            Counter(
                labels[row["runtime_ref"]]
                for row in semantic
                if row["policy_family"] == family.value
            )
        )
        for family in FAMILIES
    }
    phenomenon_actions = {
        phenomenon: sorted(
            {
                labels[row["runtime_ref"]]
                for row in semantic
                if row["semantic_phenomenon"] == phenomenon
            }
        )
        for phenomenon in {row["semantic_phenomenon"] for row in semantic}
    }
    pair_audit = _audit_semantic_pairs(authored, pairs)
    source = _root() / "app/eval/q5_frontier_k0u_handwritten.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    return {
        "schema_version": "q5-k0u-coverage-v1",
        "capability_counts": dict(Counter(row["capability_class"] for row in topology)),
        "semantic_coverage_counts": dict(Counter(row["semantic_coverage"] for row in semantic)),
        "semantic_pair_direction_by_coverage": by_slice,
        "family_counts": dict(Counter(row["policy_family"] for row in semantic)),
        "phenomenon_counts": dict(Counter(row["semantic_phenomenon"] for row in semantic)),
        "family_actions": family_actions,
        "family_action_counts": family_action_counts,
        "phenomenon_actions": phenomenon_actions,
        "global_action_counts": dict(Counter(labels[row["runtime_ref"]] for row in semantic)),
        "pair_constraints_verified": pair_audit,
        "unique_semantic_policy_text_count": len({row["policy_text"] for row in inventory}),
        "handwritten_inventory_count": len(inventory),
        "authoring_joined_string_count": sum(
            isinstance(node, ast.JoinedStr) for node in ast.walk(tree)
        ),
        "semantic_batch_renderer_present": False,
        "authoring_source_sha256": _sha(source.read_bytes()),
        "external_requests": 0,
        "model_requests": 0,
    }


def _metrics(graded):
    semantic = [row for row in graded if row["capability_class"] == "semantic_open"]
    complete = [row for row in semantic if row["parser_status"] == "complete"]
    uncovered = [row for row in semantic if row["parser_status"] == "abstain"]
    return {
        "schema_version": "q5-k0u-preaudit-metrics-v1",
        "deterministic_complete_count": len(complete),
        "deterministic_conditional_risk": sum(not row["success"] for row in complete)
        / len(complete),
        "oracle_resolvable_abstentions": len(uncovered),
        "llm_only_semantic_calls": len(semantic),
        "hybrid_semantic_calls": len(uncovered),
        "hybrid_theoretical_call_avoidance": 1 - len(uncovered) / len(semantic),
        "unsafe_terminal": sum(row["unsafe_terminal"] for row in graded),
        "external_requests": 0,
        "model_requests": 0,
    }


def _enforce(coverage, metrics):
    if coverage["capability_counts"] != {
        "symbolic_complete": 16,
        "semantic_open": 64,
        "ambiguous_or_unsafe": 16,
    }:
        raise ValueError("K0U capability topology mismatch")
    if coverage["semantic_coverage_counts"] != {
        "parser_covered": 32,
        "parser_uncovered": 32,
    }:
        raise ValueError("K0U parser coverage mismatch")
    expected_pairs = {
        "policy_fixed_state_changed": 8,
        "state_fixed_policy_changed": 8,
    }
    if any(
        value != expected_pairs
        for value in coverage["semantic_pair_direction_by_coverage"].values()
    ):
        raise ValueError("K0U pair directions are not balanced")
    if len(coverage["phenomenon_counts"]) < 6:
        raise ValueError("K0U semantic phenomenon coverage is insufficient")
    if any(len(actions) != 4 for actions in coverage["family_actions"].values()):
        raise ValueError("K0U family/action mapping is deterministic")
    if len(set(coverage["global_action_counts"].values())) != 1:
        raise ValueError("K0U global action outcomes are not balanced")
    if any(len(actions) < 4 for actions in coverage["phenomenon_actions"].values()):
        raise ValueError("K0U phenomenon/action mapping is deterministic")
    if coverage["authoring_joined_string_count"] or coverage["semantic_batch_renderer_present"]:
        raise ValueError("K0U semantic policies must be explicitly handwritten")
    if coverage["pair_constraints_verified"] != {
        "policy_fixed_state_changed": 16,
        "state_fixed_policy_changed": 16,
    }:
        raise ValueError("K0U counterfactual pair constraints failed")
    if metrics["deterministic_conditional_risk"] != 0 or metrics["unsafe_terminal"] != 0:
        raise ValueError("K0U deterministic safety metrics failed")


def _audit_semantic_pairs(authored, pairs):
    runtime = {row["runtime_ref"]: row for row in authored["runtime"]}
    policies = {row["runtime_ref"]: row["policy_ir"] for row in authored["policy_ir"]}
    verified = Counter()
    for members in pairs.values():
        first_ref, second_ref = (item["runtime_ref"] for item in members)
        first_runtime, second_runtime = runtime[first_ref], runtime[second_ref]
        first_state = first_runtime["trusted_observation"]["state"]
        second_state = second_runtime["trusted_observation"]["state"]
        direction = members[0]["pair_kind"]
        if direction == "policy_fixed_state_changed":
            if policies[first_ref] != policies[second_ref]:
                raise ValueError("policy-fixed pair changed canonical policy IR")
            if first_runtime["policy_text"] != second_runtime["policy_text"]:
                raise ValueError("policy-fixed pair changed rendered policy meaning")
            changed = {key for key in first_state if first_state[key] != second_state[key]}
            if changed != {"status"}:
                raise ValueError("policy-fixed pair must change exactly one state fact")
        elif direction == "state_fixed_policy_changed":
            if first_state != second_state:
                raise ValueError("state-fixed pair changed the semantic environment")
            first_ir, first_values = _without_status_values(policies[first_ref])
            second_ir, second_values = _without_status_values(policies[second_ref])
            if first_ir != second_ir or len(first_values) != 1 or len(second_values) != 1:
                raise ValueError("state-fixed pair must change exactly one policy clause")
            if first_values == second_values:
                raise ValueError("state-fixed pair did not change its status predicate")
        else:
            raise ValueError("unknown K0U pair direction")
        verified[direction] += 1
    return dict(verified)


def _without_status_values(policy_ir):
    clone = json.loads(json.dumps(policy_ir))
    values = []

    def visit(value):
        if isinstance(value, dict):
            if value.get("field") == "status" and "value" in value:
                values.append(value["value"])
                value["value"] = "<counterfactual-status>"
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(clone)
    return clone, values


def _prereg_receipt():
    frozen = {}
    for path in FROZEN_K0U_SOURCES:
        source = (_root() / path).read_bytes()
        committed = subprocess.run(
            ["git", "show", f"{K0U_PREREG_COMMIT}:{path}"],
            cwd=_root(),
            check=True,
            capture_output=True,
        ).stdout
        if source != committed:
            raise ValueError(f"frozen K0U prereg source changed: {path}")
        frozen[path] = {
            "git_blob_sha": _git("rev-parse", f"{K0U_PREREG_COMMIT}:{path}"),
            "source_sha256": _sha(source),
        }
    return {
        "schema_version": "q5-k0u-prereg-receipt-v1",
        "prereg_commit": K0U_PREREG_COMMIT,
        "frozen_sources": frozen,
        "external_requests": 0,
        "model_requests": 0,
    }


def _root():
    return Path(__file__).resolve().parents[2]


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=_root(), check=True, capture_output=True, text=True
    ).stdout.strip()


def _json_bytes(payload):
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _jsonl_bytes(rows):
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode()


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()
