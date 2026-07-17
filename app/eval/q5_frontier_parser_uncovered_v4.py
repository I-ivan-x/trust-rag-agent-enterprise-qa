"""Author and verify the K0SR-B parser-uncovered development package.

This module is deliberately separate from the preregistered parser/compiler
sources.  It appeared only after the K0SR-A commit was clean and immutable.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.eval.q5_frontier import _structured_clauses
from app.eval.q5_frontier_compiler_v4 import compile_policy_ir_v4
from app.eval.q5_frontier_parser_suite_v4 import best_of_deterministic_selector
from app.eval.q5_frontier_prereg_v4 import FROZEN_SOURCE_PATHS
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
from app.schemas.q5_frontier_v2 import (
    FrontierHostAuthorization,
    FrontierObservationStatus,
    FrontierObservationType,
    FrontierObservedState,
    FrontierTrustedObservation,
)
from app.schemas.q5_frontier_v4 import FrontierRuntimePayloadV4

PREREG_COMMIT = "ad3b9ea48a9df910d6816e3e5be4c1f24d747275"
PACKAGE_FILES = frozenset(
    {
        "runtime_cases.jsonl",
        "policy_ir.jsonl",
        "environment_authoring.jsonl",
        "topology.jsonl",
        "gold.jsonl",
        "execution_rows.jsonl",
        "graded_rows.jsonl",
        "headroom_report.json",
        "coverage_report.json",
        "mutation_matrix.json",
        "prereg_receipt.json",
        "dataset_manifest.json",
        "artifact_hashes.json",
    }
)
FAMILIES = tuple(FrontierResourceType)
OBSERVATION_BY_FAMILY = {
    FrontierResourceType.incident: FrontierObservationType.inspect_incident_state,
    FrontierResourceType.change: FrontierObservationType.inspect_change_state,
    FrontierResourceType.access: FrontierObservationType.inspect_access_scope,
    FrontierResourceType.retention: FrontierObservationType.inspect_retention_state,
}
PHENOMENON_BY_FAMILY = {
    FrontierResourceType.incident: "negation_unless",
    FrontierResourceType.change: "temporal_ordering",
    FrontierResourceType.access: "cross_sentence_coreference",
    FrontierResourceType.retention: "exception_precedence",
}
ACTION_PARAPHRASES = {
    FrontierDisposition.mark_stale: (
        "classify the entry as no longer current",
        "record that the item has aged out",
        "apply the obsolete-record designation",
        "move the entry into stale status",
    ),
    FrontierDisposition.remediate: (
        "begin corrective handling",
        "initiate the repair workflow",
        "put remediation in motion",
        "start corrective resolution",
    ),
    FrontierDisposition.notify: (
        "issue the required advisory",
        "deliver the policy notice",
        "communicate the prescribed alert",
        "dispatch the governance notification",
    ),
    FrontierDisposition.human_review: (
        "defer the judgment to an authorized reviewer",
        "place the decision before a person",
        "request manual adjudication",
        "route the matter for human determination",
    ),
    FrontierDisposition.no_action: (
        "preserve the record without intervention",
        "make no governance change",
        "retain the current disposition",
        "leave the governed state as it stands",
    ),
}


def build_parser_uncovered_dev_v4() -> dict[str, bytes]:
    authored = _author_rows()
    pair_audit = _audit_pairs(authored)
    execution = _execute(authored["runtime"])
    gold = _grade_gold(authored["runtime"], authored["policy_ir"])
    graded = _grade(execution, gold, authored["topology"])
    complete = [row for row in graded if row["parser_status"] == "complete"]
    abstained = [row for row in graded if row["parser_status"] == "abstain"]
    if len(graded) != 80 or len(abstained) < 16:
        raise ValueError("parser-uncovered development thresholds are not met")
    if not all(row["success"] for row in complete):
        raise ValueError("deterministic conditional risk must remain zero")
    semantic_abstentions = [
        row
        for row in abstained
        if row["capability_class"] == "semantic_open"
    ]
    coverage = {
        "schema_version": "q5-parser-uncovered-coverage-v1",
        "case_count": len(graded),
        "parser_uncovered_case_count": len(semantic_abstentions),
        "family_counts": dict(Counter(row["policy_family"] for row in graded)),
        "phenomenon_counts": dict(
            Counter(row["semantic_phenomenon"] for row in semantic_abstentions)
        ),
        "unique_policy_text_count": len(
            {row["policy_text"] for row in authored["runtime"]}
        ),
        "authored_action_paraphrase_count": 10,
        "pair_audit": pair_audit,
        "external_requests": 0,
        "model_requests": 0,
    }
    headroom = {
        "schema_version": "q5-parser-uncovered-headroom-report-v1",
        "oracle_resolvable_abstentions": len(semantic_abstentions),
        "family_coverage": sorted(
            {row["policy_family"] for row in semantic_abstentions}
        ),
        "phenomenon_coverage": sorted(
            {row["semantic_phenomenon"] for row in semantic_abstentions}
        ),
        "deterministic_conditional_risk": 0.0,
        "call_headroom": {
            "protocol_frozen": True,
            "llm_only_semantic_calls": len(semantic_abstentions),
            "hybrid_semantic_calls": len(semantic_abstentions),
            "avoided_calls": 0,
        },
        "token_avoidance": "not_evaluated",
    }
    receipt = _prereg_receipt()
    mutation_matrix = {
        "schema_version": "q5-parser-uncovered-mutation-matrix-v1",
        "categories": {
            "structural": [
                {"mutation": "missing_artifact", "expected_outcome": "reject"},
                {"mutation": "extra_artifact", "expected_outcome": "reject"},
                {"mutation": "duplicate_runtime_ref", "expected_outcome": "reject"},
            ],
            "semantic": [
                {"mutation": "gold_disposition", "expected_outcome": "reject"},
                {"mutation": "policy_ir_clause", "expected_outcome": "reject"},
                {"mutation": "observation_family", "expected_outcome": "safe_human_review"},
                {"mutation": "requirement_flag_false", "expected_outcome": "reject"},
            ],
            "artifact": [
                {"mutation": "prereg_commit", "expected_outcome": "reject"},
                {"mutation": "parser_blob", "expected_outcome": "reject"},
                {"mutation": "source_sha", "expected_outcome": "reject"},
                {"mutation": "rehashed_graded_row", "expected_outcome": "reject"},
            ],
        },
    }
    manifest = {
        "schema_version": "q5-parser-uncovered-dev-manifest-v1",
        "partition": "parser_uncovered_dev",
        "case_count": len(graded),
        "parser_uncovered_case_count": len(semantic_abstentions),
        "family_count": len(coverage["family_counts"]),
        "phenomenon_count": len(coverage["phenomenon_counts"]),
        "prereg_commit": PREREG_COMMIT,
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
        "headroom_report.json": _json_bytes(headroom),
        "coverage_report.json": _json_bytes(coverage),
        "mutation_matrix.json": _json_bytes(mutation_matrix),
        "prereg_receipt.json": _json_bytes(receipt),
        "dataset_manifest.json": _json_bytes(manifest),
    }
    raw["artifact_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-parser-uncovered-artifact-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_parser_uncovered_dev_v4(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"parser-uncovered output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_parser_uncovered_dev_v4()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["dataset_manifest.json"])


def verify_parser_uncovered_dev_v4(
    output_dir: Path | str,
    *,
    require_parent_commit: bool = False,
) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != PACKAGE_FILES:
        raise ValueError("parser-uncovered artifact closure mismatch")
    expected = build_parser_uncovered_dev_v4()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"parser-uncovered recomputation mismatch: {name}")
    _verify_prereg_receipt(
        json.loads(expected["prereg_receipt.json"]),
        require_parent_commit=require_parent_commit,
    )
    return json.loads(expected["dataset_manifest.json"])


def _author_rows() -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counter = 0
    legal = [item.value for item in FrontierDisposition]
    for family in FAMILIES:
        for local_index in range(20):
            counter += 1
            runtime_ref = f"parser-uncovered-dev-resource:r{counter:03d}"
            pair_number = local_index // 2
            pair_kind = (
                "policy_fixed_state_changed"
                if pair_number < 5
                else "state_fixed_policy_changed"
            )
            target = f"{family.value}_trigger_{pair_number}"
            alternate = f"{family.value}_alternate_{pair_number}"
            if pair_kind == "policy_fixed_state_changed":
                policy_value = target
                state_value = target if local_index % 2 == 0 else alternate
            else:
                state_value = target
                policy_value = target if local_index % 2 == 0 else alternate
            true_disposition = _family_disposition(family)
            policy_ir = _policy_ir(family, policy_value, true_disposition)
            semantic = local_index >= 16
            policy_text = (
                _semantic_text(
                    family,
                    local_index,
                    policy_value,
                    true_disposition,
                )
                if semantic
                else "Q5POLICYv5; " + "; ".join(_structured_clauses(policy_ir))
            )
            observation = FrontierTrustedObservation(
                observation_type=OBSERVATION_BY_FAMILY[family],
                status=FrontierObservationStatus.ok,
                success=True,
                authorization=FrontierHostAuthorization(
                    authorized=True,
                    authorized_evidence_ids=[f"chunk:parser-uncovered-{counter:03d}"],
                ),
                request_id=f"observation:parser-uncovered-{counter:03d}",
                state=FrontierObservedState(
                    status=state_value,
                    scope="production",
                    temporal_state="current",
                    exception_active=False,
                ),
            )
            runtime = FrontierRuntimePayloadV4(
                runtime_ref=runtime_ref,
                policy_text=policy_text,
                query="Determine the policy disposition from the authorized observation.",
                legal_dispositions=legal,
                trusted_observation=observation,
            )
            rows["runtime"].append(runtime.model_dump(mode="json"))
            rows["policy_ir"].append(
                {"runtime_ref": runtime_ref, "policy_ir": policy_ir.model_dump(mode="json")}
            )
            rows["environment"].append(
                {
                    "runtime_ref": runtime_ref,
                    "trusted_observation": observation.model_dump(mode="json"),
                }
            )
            rows["topology"].append(
                {
                    "runtime_ref": runtime_ref,
                    "capability_class": "semantic_open" if semantic else "symbolic_complete",
                    "policy_family": family.value,
                    "semantic_phenomenon": (
                        PHENOMENON_BY_FAMILY[family] if semantic else "structured_policy"
                    ),
                    "pair_id": f"parser-uncovered-{family.value}-p{pair_number:02d}",
                    "pair_kind": pair_kind,
                }
            )
    return rows


def _policy_ir(
    family: FrontierResourceType,
    policy_value: str,
    true_disposition: FrontierDisposition,
) -> CanonicalPolicyIR:
    return CanonicalPolicyIR(
        scope=FrontierPolicyScope(resource_type=family, allowed_scopes=["production"]),
        condition=FrontierConditionExpression(
            all_of=[
                FrontierPredicate(
                    field=FrontierPredicateField.status,
                    operator=FrontierPredicateOperator.eq,
                    value=policy_value,
                )
            ]
        ),
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
        true_disposition=true_disposition,
        false_disposition=FrontierDisposition.no_action,
        ambiguity=FrontierAmbiguityConflict(),
        terminal_safety=FrontierTerminalSafetyConstraints(
            allowed_dispositions=list(FrontierDisposition)
        ),
    )


def _semantic_text(
    family: FrontierResourceType,
    local_index: int,
    policy_value: str,
    disposition: FrontierDisposition,
) -> str:
    slot = (local_index // 2) % 4
    action = ACTION_PARAPHRASES[disposition][slot]
    quiet = ACTION_PARAPHRASES[FrontierDisposition.no_action][(slot + 1) % 4]
    templates = {
        FrontierResourceType.incident: (
            "Unless the observed incident status differs from {value}, treat that fact as "
            "the trigger. If it is the trigger, {action}; if not, {quiet}.",
            "Do not withhold {action} when the incident status is {value}. The contrary "
            "status means {quiet}.",
            "The incident qualifies except when its status is not {value}; the qualifying "
            "branch says to {action}, and the exception says to {quiet}.",
            "Only a status other than {value} defeats the antecedent. Otherwise, {action}; "
            "on defeat, {quiet}.",
        ),
        FrontierResourceType.change: (
            "First establish the change status. Once it has become {value}, {action}; until "
            "that transition, {quiet}.",
            "After the observation records {value} for the change, the later duty is to "
            "{action}. Before then, {quiet}.",
            "The earlier state controls until {value} is observed. Thereafter, {action}; "
            "otherwise, {quiet}.",
            "When the change reaches {value}, that temporal milestone requires us to "
            "{action}. In its absence, {quiet}.",
        ),
        FrontierResourceType.access: (
            "An access record is qualifying when its status is {value}. That qualification "
            "means {action}; without it, {quiet}.",
            "Look for access status {value}. If the preceding condition holds, {action}; "
            "when it does not, {quiet}.",
            "Status {value} supplies the access antecedent. This is the fact that calls for "
            "{action}; the other branch calls for {quiet}.",
            "The access condition is status {value}. It, and not a different status, entails "
            "that we {action}; otherwise, {quiet}.",
        ),
        FrontierResourceType.retention: (
            "Ordinarily, retention status {value} directs us to {action}; otherwise, "
            "{quiet}. A declared exception would take priority over that ordinary branch.",
            "For retention, {value} supports the instruction to {action}, with {quiet} as "
            "the alternative; exception precedence remains superior.",
            "Apply the base retention rule: status {value} means {action}, else {quiet}. "
            "An active exception outranks this base result.",
            "The retention branch for {value} says to {action}; its complement says to "
            "{quiet}. Any active exception is considered first.",
        ),
    }
    return templates[family][slot].format(value=policy_value, action=action, quiet=quiet)


def _audit_pairs(authored: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    runtime = {row["runtime_ref"]: row for row in authored["runtime"]}
    policy = {row["runtime_ref"]: row["policy_ir"] for row in authored["policy_ir"]}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in authored["topology"]:
        grouped[row["pair_id"]].append(row)
    counts = Counter()
    for pair_id, members in grouped.items():
        if len(members) != 2:
            raise ValueError(f"incomplete parser-uncovered pair: {pair_id}")
        first, second = [item["runtime_ref"] for item in members]
        kind = members[0]["pair_kind"]
        if kind == "policy_fixed_state_changed":
            if policy[first] != policy[second]:
                raise ValueError(f"policy-fixed pair changed Policy IR: {pair_id}")
            if runtime[first]["policy_text"] != runtime[second]["policy_text"]:
                raise ValueError(f"policy-fixed pair changed rendering: {pair_id}")
            left = runtime[first]["trusted_observation"]["state"]
            right = runtime[second]["trusted_observation"]["state"]
            changed = {key for key in left if left[key] != right[key]}
            if changed != {"status"}:
                raise ValueError(f"policy-fixed pair must change one state fact: {pair_id}")
        else:
            left = runtime[first]["trusted_observation"]["state"]
            right = runtime[second]["trusted_observation"]["state"]
            if left != right:
                raise ValueError(f"state-fixed pair changed runtime state: {pair_id}")
            left_ir = json.loads(json.dumps(policy[first]))
            right_ir = json.loads(json.dumps(policy[second]))
            left_value = left_ir["condition"]["all_of"][0].pop("value")
            right_value = right_ir["condition"]["all_of"][0].pop("value")
            if left_ir != right_ir or left_value == right_value:
                raise ValueError(f"state-fixed pair must change one policy clause: {pair_id}")
        counts[kind] += 1
    return {
        "pair_count": len(grouped),
        "pair_kind_counts": dict(counts),
        "canonical_pair_constraints_verified": True,
    }


def _family_disposition(family: FrontierResourceType) -> FrontierDisposition:
    return {
        FrontierResourceType.incident: FrontierDisposition.remediate,
        FrontierResourceType.change: FrontierDisposition.notify,
        FrontierResourceType.access: FrontierDisposition.human_review,
        FrontierResourceType.retention: FrontierDisposition.mark_stale,
    }[family]


def _execute(runtime_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for raw in runtime_rows:
        runtime = FrontierRuntimePayloadV4.model_validate(raw)
        parsed = best_of_deterministic_selector(runtime)
        disposition = FrontierDisposition.human_review
        if parsed.policy_ir is not None:
            disposition = compile_policy_ir_v4(parsed.policy_ir, runtime).disposition
        rows.append(
            {
                "runtime_ref": runtime.runtime_ref,
                "parser_status": parsed.status,
                "parser_reason": parsed.reason,
                "terminal_disposition": disposition.value,
                "external_requests": 0,
                "model_requests": 0,
            }
        )
    return rows


def _grade_gold(runtime_rows, policy_rows):
    policies = {
        row["runtime_ref"]: CanonicalPolicyIR.model_validate(row["policy_ir"])
        for row in policy_rows
    }
    rows = []
    for raw in runtime_rows:
        runtime = FrontierRuntimePayloadV4.model_validate(raw)
        result = compile_policy_ir_v4(policies[runtime.runtime_ref], runtime)
        rows.append({"runtime_ref": runtime.runtime_ref, "disposition": result.disposition.value})
    return rows


def _grade(execution, gold, topology):
    gold_by_ref = {row["runtime_ref"]: row for row in gold}
    top_by_ref = {row["runtime_ref"]: row for row in topology}
    return [
        {
            **top_by_ref[row["runtime_ref"]],
            **row,
            "gold_disposition": gold_by_ref[row["runtime_ref"]]["disposition"],
            "success": row["terminal_disposition"]
            == gold_by_ref[row["runtime_ref"]]["disposition"],
        }
        for row in execution
    ]


def _prereg_receipt() -> dict[str, Any]:
    files = {}
    for path in FROZEN_SOURCE_PATHS:
        blob = _git("rev-parse", f"{PREREG_COMMIT}:{path}")
        source = _project_path(path).read_bytes()
        committed_source = subprocess.run(
            ["git", "show", f"{PREREG_COMMIT}:{path}"],
            cwd=_project_root(),
            check=True,
            capture_output=True,
        ).stdout
        if source != committed_source:
            raise ValueError(f"frozen prereg source changed after commit: {path}")
        files[path] = {
            "git_blob_sha": blob,
            "source_sha256": _sha(source),
        }
    return {
        "schema_version": "q5-parser-uncovered-prereg-receipt-v1",
        "prereg_commit": PREREG_COMMIT,
        "expected_execution_parent": PREREG_COMMIT,
        "frozen_sources": files,
        "parser_blob_identical_to_parent": True,
        "external_requests": 0,
        "model_requests": 0,
    }


def _verify_prereg_receipt(receipt, *, require_parent_commit):
    if receipt != _prereg_receipt():
        raise ValueError("preregistration receipt recomputation mismatch")
    if require_parent_commit:
        parent = _git("rev-parse", "HEAD^")
        if parent != receipt["prereg_commit"]:
            raise ValueError("execution commit parent is not the prereg commit")
        for path, identity in receipt["frozen_sources"].items():
            if _git("rev-parse", f"HEAD:{path}") != identity["git_blob_sha"]:
                raise ValueError(f"frozen parser/compiler blob changed in B: {path}")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=_project_root(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _project_path(path: str) -> Path:
    return _project_root() / path


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
