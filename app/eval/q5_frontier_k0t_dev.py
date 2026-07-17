"""K0T-B authoring and execution, created after the K0T-A prereg commit."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.eval.q5_frontier import _structured_clauses, structured_grammar_parser
from app.eval.q5_frontier_attack_suite_v5 import lexical_condition_action_parser
from app.eval.q5_frontier_compiler_v4 import compile_policy_ir_v4
from app.eval.q5_frontier_k0t_contract import (
    K0T_ACTION_PHRASES,
    K0T_CALL_PROTOCOL,
)
from app.eval.q5_frontier_k0t_prereg import FROZEN_K0T_SOURCES
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
from app.schemas.q5_frontier_v5 import FrontierRuntimePayloadV5

K0T_PREREG_COMMIT = "139378c62534660b2a50d771ef6d2c010b00cb62"
K0T_DEV_FILES = frozenset(
    {
        "runtime_cases.jsonl",
        "policy_ir.jsonl",
        "environment_authoring.jsonl",
        "topology.jsonl",
        "gold.jsonl",
        "execution_rows.jsonl",
        "graded_rows.jsonl",
        "coverage_report.json",
        "metric_report.json",
        "dataset_manifest.json",
        "prereg_receipt.json",
        "artifact_hashes.json",
    }
)
FAMILIES = tuple(FrontierResourceType)
PHENOMENA = (
    "negation_unless",
    "temporal_ordering",
    "cross_sentence_coreference",
    "exception_precedence",
)
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


def build_k0t_dev_artifacts() -> dict[str, bytes]:
    authored = _author_k0t_rows()
    gold = _offline_gold(authored["runtime"], authored["policy_ir"])
    execution = _execute_without_labels(authored["runtime"])
    graded = _grade(execution, authored["topology"], gold)
    coverage = _coverage(authored, gold)
    metrics = _metrics(graded)
    _enforce_constraints(coverage, metrics)
    receipt = _prereg_receipt()
    manifest = {
        "schema_version": "q5-k0t-dev-manifest-v1",
        "partition": "parser_uncovered_dev",
        "case_count": 96,
        "capability_counts": coverage["capability_counts"],
        "semantic_coverage_counts": coverage["semantic_coverage_counts"],
        "prereg_commit": K0T_PREREG_COMMIT,
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
        "coverage_report.json": _json_bytes(coverage),
        "metric_report.json": _json_bytes(metrics),
        "dataset_manifest.json": _json_bytes(manifest),
        "prereg_receipt.json": _json_bytes(receipt),
    }
    raw["artifact_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-k0t-dev-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_k0t_dev(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"K0T dev output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_k0t_dev_artifacts()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["dataset_manifest.json"])


def verify_k0t_dev(
    output_dir: Path | str,
    *,
    require_parent_commit: bool = False,
) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != K0T_DEV_FILES:
        raise ValueError("K0T dev artifact closure mismatch")
    expected = build_k0t_dev_artifacts()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"K0T dev recomputation mismatch: {name}")
    _verify_prereg_receipt(
        json.loads(expected["prereg_receipt.json"]),
        require_parent_commit=require_parent_commit,
    )
    return json.loads(expected["dataset_manifest.json"])


def _author_k0t_rows() -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counter = 0
    # 16 structured symbolic cases.
    for family_index, family in enumerate(FAMILIES):
        for local in range(4):
            counter += 1
            value = f"signal_{counter:03d}"
            state = value if local % 2 == 0 else f"neutral_{counter:03d}"
            ir = _policy_ir(
                family,
                value,
                SEMANTIC_ACTIONS[(family_index + local) % 4],
                SEMANTIC_ACTIONS[(family_index + local + 1) % 4],
            )
            _append_case(
                rows,
                counter,
                family,
                "symbolic_complete",
                "structured_policy",
                "symbolic",
                f"k0t-symbolic-{family.value}-{local}",
                "none",
                ir,
                state,
                "Q5POLICYv5; " + "; ".join(_structured_clauses(ir)),
            )
    # 64 semantic cases: 32 covered and 32 uncovered.
    for coverage_index, coverage in enumerate(("parser_covered", "parser_uncovered")):
        for pair_index in range(16):
            family_index = pair_index % 4
            phenomenon_index = pair_index // 4
            family = FAMILIES[family_index]
            phenomenon = PHENOMENA[phenomenon_index]
            direction = (
                "policy_fixed_state_changed"
                if phenomenon_index % 2 == 0
                else "state_fixed_policy_changed"
            )
            same_outcome = (phenomenon_index + coverage_index) % 2 == 0
            true_action = SEMANTIC_ACTIONS[
                (family_index + phenomenon_index + coverage_index) % 4
            ]
            false_action = SEMANTIC_ACTIONS[
                (family_index + phenomenon_index + coverage_index + 1) % 4
            ]
            base = 100 + coverage_index * 100 + pair_index * 3
            target_value = f"signal_{base:03d}"
            first_alt = f"neutral_{base + 1:03d}"
            second_alt = f"neutral_{base + 2:03d}"
            for member in range(2):
                counter += 1
                if direction == "policy_fixed_state_changed":
                    policy_value = target_value
                    if same_outcome:
                        state_value = first_alt if member == 0 else second_alt
                    else:
                        state_value = target_value if member == 0 else first_alt
                else:
                    state_value = target_value
                    if same_outcome:
                        policy_value = first_alt if member == 0 else second_alt
                    else:
                        policy_value = target_value if member == 0 else first_alt
                ir = _policy_ir(
                    family,
                    policy_value,
                    true_action,
                    false_action,
                )
                phrase_slot = (
                    family_index * 2 + phenomenon_index + coverage_index
                ) % 4
                true_phrase = K0T_ACTION_PHRASES[true_action][phrase_slot]
                false_phrase = K0T_ACTION_PHRASES[false_action][(phrase_slot + 1) % 4]
                policy_text = (
                    _covered_text(
                        family,
                        policy_value,
                        true_phrase,
                        false_phrase,
                    )
                    if coverage == "parser_covered"
                    else _uncovered_text(
                        phenomenon,
                        family,
                        policy_value,
                        true_phrase,
                        false_phrase,
                    )
                )
                _append_case(
                    rows,
                    counter,
                    family,
                    "semantic_open",
                    phenomenon,
                    coverage,
                    f"k0t-{coverage}-{phenomenon}",
                    f"k0t-{coverage}-pair-{pair_index:02d}",
                    ir,
                    state_value,
                    policy_text,
                    pair_kind=direction,
                )
    # 16 ambiguous/unsafe cases, all forced to a safe terminal.
    for family_index, family in enumerate(FAMILIES):
        for local in range(4):
            counter += 1
            value = f"signal_{500 + counter:03d}"
            ir = _policy_ir(
                family,
                value,
                SEMANTIC_ACTIONS[(family_index + local) % 4],
                SEMANTIC_ACTIONS[(family_index + local + 1) % 4],
                ambiguous=True,
            )
            _append_case(
                rows,
                counter,
                family,
                "ambiguous_or_unsafe",
                "conflict_or_authorization",
                "unsafe",
                f"k0t-unsafe-{family.value}-{local}",
                "none",
                ir,
                value,
                "Deliberate conflict: two governing clauses cannot be reconciled.",
                authorized=local % 2 == 0,
                success=local < 2,
            )
    if counter != 96:
        raise AssertionError("K0T authoring must create exactly 96 cases")
    return rows


def _append_case(
    rows,
    counter,
    family,
    capability,
    phenomenon,
    coverage,
    renderer_id,
    pair_id,
    ir,
    state_value,
    policy_text,
    *,
    pair_kind="none",
    authorized=True,
    success=True,
):
    runtime_ref = f"frontier-k0t-dev-resource:r{counter:03d}"
    observation = FrontierTrustedObservation(
        observation_type=OBSERVATION_BY_FAMILY[family],
        status=FrontierObservationStatus.ok if success else FrontierObservationStatus.timeout,
        success=success,
        authorization=FrontierHostAuthorization(
            authorized=authorized,
            authorized_evidence_ids=(
                [f"chunk:k0t-{counter:03d}"] if authorized and success else []
            ),
        ),
        request_id=f"observation:k0t-{counter:03d}",
        state=(
            FrontierObservedState(
                status=state_value,
                scope="production",
                temporal_state="current",
                exception_active=False,
            )
            if success
            else None
        ),
    )
    runtime = FrontierRuntimePayloadV5(
        runtime_ref=runtime_ref,
        policy_text=policy_text,
        query="Apply the policy to the authorized typed observation.",
        legal_dispositions=list(FrontierDisposition),
        trusted_observation=observation,
    )
    rows["runtime"].append(runtime.model_dump(mode="json"))
    rows["policy_ir"].append(
        {"runtime_ref": runtime_ref, "policy_ir": ir.model_dump(mode="json")}
    )
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
            "renderer_id": renderer_id,
            "pair_id": pair_id,
            "pair_kind": pair_kind,
        }
    )


def _policy_ir(family, value, true_action, false_action, *, ambiguous=False):
    return CanonicalPolicyIR(
        scope=FrontierPolicyScope(resource_type=family, allowed_scopes=["production"]),
        condition=FrontierConditionExpression(
            all_of=[
                FrontierPredicate(
                    field=FrontierPredicateField.status,
                    operator=FrontierPredicateOperator.eq,
                    value=value,
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
        true_disposition=true_action,
        false_disposition=false_action,
        ambiguity=(
            FrontierAmbiguityConflict(
                kind=FrontierAmbiguityKind.conflicting_clauses,
                conflict_count=2,
            )
            if ambiguous
            else FrontierAmbiguityConflict()
        ),
        terminal_safety=FrontierTerminalSafetyConstraints(
            allowed_dispositions=list(FrontierDisposition)
        ),
    )


def _covered_text(family, value, true_phrase, false_phrase):
    article = (
        "an"
        if family in {FrontierResourceType.incident, FrontierResourceType.access}
        else "a"
    )
    return (
        f"For {article} {family.value} record, when status equals {value}, "
        f"{true_phrase}; otherwise, {false_phrase}."
    )


def _uncovered_text(phenomenon, family, value, true_phrase, false_phrase):
    templates = {
        "negation_unless": (
            "Unless its observed status differs from {value}, the {family} antecedent "
            "holds. In that event, {true}; if the antecedent is defeated, {false}."
        ),
        "temporal_ordering": (
            "First observe the {family} status. Once {value} has been recorded, {true}; "
            "before that point, {false}."
        ),
        "cross_sentence_coreference": (
            "A {family} record qualifies when its status matches {value}. That prior "
            "qualification calls for us to {true}; without it, {false}."
        ),
        "exception_precedence": (
            "Ordinarily, {family} status {value} means we {true}, and a different status "
            "means we {false}. An active exception would outrank that ordinary branch."
        ),
    }
    return templates[phenomenon].format(
        family=family.value,
        value=value,
        true=true_phrase,
        false=false_phrase,
    )


def _offline_gold(runtime_rows, policy_rows):
    policies = {
        row["runtime_ref"]: CanonicalPolicyIR.model_validate(row["policy_ir"])
        for row in policy_rows
    }
    gold = []
    for raw in runtime_rows:
        runtime = FrontierRuntimePayloadV5.model_validate(raw)
        result = compile_policy_ir_v4(
            policies[runtime.runtime_ref], _as_v4(runtime)
        )
        gold.append({"runtime_ref": runtime.runtime_ref, "disposition": result.disposition.value})
    return gold


def _execute_without_labels(runtime_rows):
    rows = []
    for raw in runtime_rows:
        runtime = FrontierRuntimePayloadV5.model_validate(raw)
        if runtime.policy_text.startswith("Q5POLICYv5;"):
            parsed = structured_grammar_parser(runtime.policy_text)
            if parsed.status == "complete":
                terminal = compile_policy_ir_v4(parsed.parsed_ir, _as_v4(runtime)).disposition.value
                status = "complete"
            else:
                terminal, status = "human_review", parsed.status
        else:
            state = runtime.trusted_observation.state
            lexical = (
                lexical_condition_action_parser(runtime.policy_text, state.status)
                if state is not None
                else None
            )
            if lexical is not None and runtime.trusted_observation.authorization.authorized:
                terminal, status = lexical, "complete"
            elif "Deliberate conflict:" in runtime.policy_text:
                terminal, status = "human_review", "ambiguous"
            else:
                terminal, status = "human_review", "abstain"
        rows.append(
            {
                "runtime_ref": runtime.runtime_ref,
                "parser_status": status,
                "terminal_disposition": terminal,
                "external_requests": 0,
                "model_requests": 0,
            }
        )
    return rows


def _as_v4(runtime):
    return FrontierRuntimePayloadV4(
        runtime_ref=runtime.runtime_ref.replace(
            "frontier-k0t-dev-resource", "parser-uncovered-dev-resource"
        ),
        policy_text=runtime.policy_text,
        query=runtime.query,
        legal_dispositions=runtime.legal_dispositions,
        trusted_observation=runtime.trusted_observation,
    )


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


def _coverage(authored, gold):
    topology = authored["topology"]
    runtime = {row["runtime_ref"]: row for row in authored["runtime"]}
    policies = {row["runtime_ref"]: row["policy_ir"] for row in authored["policy_ir"]}
    labels = {row["runtime_ref"]: row["disposition"] for row in gold}
    semantic = [row for row in topology if row["capability_class"] == "semantic_open"]
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in semantic:
        pairs[row["pair_id"]].append(row)
    _audit_pairs(pairs, runtime, policies)
    phrases = {
        phrase
        for raw in runtime.values()
        for values in K0T_ACTION_PHRASES.values()
        for phrase in values
        if phrase in raw["policy_text"]
    }
    family_actions = {
        family.value: sorted(
            {labels[row["runtime_ref"]] for row in semantic if row["policy_family"] == family.value}
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
        for phenomenon in PHENOMENA
    }
    values = [
        row["policy_ir"]["condition"]["all_of"][0]["value"]
        for row in authored["policy_ir"]
    ]
    banned = ("incident", "change", "access", "retention", "pair", "branch", "action")
    return {
        "schema_version": "q5-k0t-coverage-v1",
        "capability_counts": dict(Counter(row["capability_class"] for row in topology)),
        "semantic_coverage_counts": dict(Counter(row["semantic_coverage"] for row in semantic)),
        "semantic_pair_direction_counts": dict(Counter(row["pair_kind"] for row in semantic)) | {
            "pair_count": len(pairs)
        },
        "semantic_pair_direction_by_coverage": {
            coverage: dict(
                Counter(
                    members[0]["pair_kind"]
                    for members in pairs.values()
                    if members[0]["semantic_coverage"] == coverage
                )
            )
            for coverage in ("parser_covered", "parser_uncovered")
        },
        "family_counts": dict(Counter(row["policy_family"] for row in semantic)),
        "phenomenon_counts": dict(Counter(row["semantic_phenomenon"] for row in semantic)),
        "family_actions": family_actions,
        "phenomenon_actions": phenomenon_actions,
        "false_branch_dispositions": sorted(
            {row["policy_ir"]["false_disposition"] for row in authored["policy_ir"]}
        ),
        "unique_policy_text_count": len({row["policy_text"] for row in runtime.values()}),
        "observed_action_phrase_count": len(phrases),
        "policy_state_values_are_label_neutral": not any(
            token in str(value) for value in values for token in banned
        ),
        "phenomena_cross_all_families": all(
            {row["policy_family"] for row in semantic if row["semantic_phenomenon"] == phenomenon}
            == {family.value for family in FAMILIES}
            for phenomenon in PHENOMENA
        ),
        "pair_constraints_verified": True,
        "external_requests": 0,
        "model_requests": 0,
    }


def _audit_pairs(pairs, runtime, policies):
    for pair_id, members in pairs.items():
        if len(members) != 2:
            raise ValueError(f"incomplete semantic pair: {pair_id}")
        left, right = [item["runtime_ref"] for item in members]
        kind = members[0]["pair_kind"]
        if kind == "policy_fixed_state_changed":
            policy_changed = policies[left] != policies[right]
            rendering_changed = (
                runtime[left]["policy_text"] != runtime[right]["policy_text"]
            )
            if policy_changed or rendering_changed:
                raise ValueError(f"policy-fixed pair changed policy: {pair_id}")
            lstate = runtime[left]["trusted_observation"]["state"]
            rstate = runtime[right]["trusted_observation"]["state"]
            if {key for key in lstate if lstate[key] != rstate[key]} != {"status"}:
                raise ValueError(f"policy-fixed pair changed more than status: {pair_id}")
        else:
            left_state = runtime[left]["trusted_observation"]["state"]
            right_state = runtime[right]["trusted_observation"]["state"]
            if left_state != right_state:
                raise ValueError(f"state-fixed pair changed state: {pair_id}")
            first = json.loads(json.dumps(policies[left]))
            second = json.loads(json.dumps(policies[right]))
            one = first["condition"]["all_of"][0].pop("value")
            two = second["condition"]["all_of"][0].pop("value")
            if first != second or one == two:
                raise ValueError(f"state-fixed pair must change one policy value: {pair_id}")


def _metrics(graded):
    semantic = [row for row in graded if row["capability_class"] == "semantic_open"]
    completed = [row for row in semantic if row["parser_status"] == "complete"]
    errors = sum(not row["success"] for row in completed)
    unsafe = sum(row["unsafe_terminal"] for row in graded)
    return {
        "schema_version": "q5-k0t-metrics-v1",
        "deterministic_complete_count": len(completed),
        "deterministic_conditional_risk": errors / len(completed),
        "parser_uncovered": sum(row["parser_status"] == "abstain" for row in semantic),
        "llm_only_semantic_calls": K0T_CALL_PROTOCOL["llm_only_semantic_calls"],
        "hybrid_semantic_calls": K0T_CALL_PROTOCOL["hybrid_semantic_calls"],
        "semantic_call_avoidance": K0T_CALL_PROTOCOL["theoretical_call_avoidance"],
        "unsafe_terminal": unsafe,
        "token_avoidance": "not_evaluated_before_model_run",
        "external_requests": 0,
        "model_requests": 0,
    }


def _enforce_constraints(coverage, metrics):
    if coverage["capability_counts"] != {
        "symbolic_complete": 16,
        "semantic_open": 64,
        "ambiguous_or_unsafe": 16,
    }:
        raise ValueError("K0T capability topology mismatch")
    if coverage["semantic_coverage_counts"] != {
        "parser_covered": 32,
        "parser_uncovered": 32,
    }:
        raise ValueError("K0T semantic coverage topology mismatch")
    expected_directions = {
        "policy_fixed_state_changed": 8,
        "state_fixed_policy_changed": 8,
    }
    if any(
        counts != expected_directions
        for counts in coverage["semantic_pair_direction_by_coverage"].values()
    ):
        raise ValueError("K0T pair directions are not balanced within coverage slices")
    if metrics["deterministic_conditional_risk"] != 0 or metrics["unsafe_terminal"] != 0:
        raise ValueError("K0T deterministic safety constraints failed")
    if any(len(actions) < 4 for actions in coverage["family_actions"].values()):
        raise ValueError("family-to-action mapping remains deterministic")
    if any(len(actions) < 4 for actions in coverage["phenomenon_actions"].values()):
        raise ValueError("phenomenon-to-action mapping remains deterministic")
    if coverage["false_branch_dispositions"] == ["no_action"]:
        raise ValueError("false branch cannot be fixed to no_action")
    if not coverage["policy_state_values_are_label_neutral"]:
        raise ValueError("policy/state values expose labels")


def _prereg_receipt():
    files = {}
    for path in FROZEN_K0T_SOURCES:
        source = (_root() / path).read_bytes()
        committed = subprocess.run(
            ["git", "show", f"{K0T_PREREG_COMMIT}:{path}"],
            cwd=_root(),
            check=True,
            capture_output=True,
        ).stdout
        if source != committed:
            raise ValueError(f"frozen K0T-A source changed: {path}")
        files[path] = {
            "git_blob_sha": _git("rev-parse", f"{K0T_PREREG_COMMIT}:{path}"),
            "source_sha256": _sha(source),
        }
    return {
        "schema_version": "q5-k0t-prereg-receipt-v1",
        "prereg_commit": K0T_PREREG_COMMIT,
        "frozen_sources": files,
        "external_requests": 0,
        "model_requests": 0,
    }


def _verify_prereg_receipt(receipt, *, require_parent_commit):
    if receipt != _prereg_receipt():
        raise ValueError("K0T prereg receipt mismatch")
    if require_parent_commit and _git("rev-parse", "HEAD^") != K0T_PREREG_COMMIT:
        raise ValueError("K0T-B parent is not K0T-A")
    if require_parent_commit:
        for path, identity in receipt["frozen_sources"].items():
            if _git("rev-parse", f"HEAD:{path}") != identity["git_blob_sha"]:
                raise ValueError(f"K0T-B changed frozen A source: {path}")


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
