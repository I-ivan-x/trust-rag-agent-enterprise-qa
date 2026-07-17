"""K0T-C independent shortcut audit over the immutable K0T-B package."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.eval.q5_frontier_attack_suite_v5 import evaluate_shortcut_attacks
from app.eval.q5_frontier_k0t_contract import K0T_ACTION_PHRASES, K0T_K1_THRESHOLDS
from app.eval.q5_frontier_k0t_dev import verify_k0t_dev
from app.eval.q5_frontier_k0t_prereg import FROZEN_K0T_SOURCES
from app.schemas.q5_frontier import FrontierDisposition

K0T_DATA_COMMIT = "9e473815cfbdb093eb5b271355dbf4a492920de6"
AUDIT_FILES = frozenset(
    {
        "shortcut_audit.json",
        "k1_readiness.json",
        "attack_report.md",
        "source_dataset_hashes.json",
        "lineage_receipt.json",
        "audit_hashes.json",
    }
)


def build_k0t_attack_audit(
    dev_dir: Path | str = Path("data/q5_frontier/dev-k0t"),
) -> dict[str, bytes]:
    source = Path(dev_dir)
    verify_k0t_dev(source)
    runtime = _jsonl(source / "runtime_cases.jsonl")
    topology = _jsonl(source / "topology.jsonl")
    gold = _jsonl(source / "gold.jsonl")
    audit = evaluate_shortcut_attacks(runtime, topology, gold).model_dump(mode="json")
    metrics = _json(source / "metric_report.json")
    coverage = _json(source / "coverage_report.json")
    phrase_audit = _action_phrase_audit(runtime, topology)
    checks = {
        "deterministic_conditional_risk": metrics["deterministic_conditional_risk"]
        <= K0T_K1_THRESHOLDS["deterministic_conditional_risk_max"],
        "parser_uncovered": metrics["parser_uncovered"]
        >= K0T_K1_THRESHOLDS["parser_uncovered_min"],
        "semantic_call_avoidance": metrics["semantic_call_avoidance"]
        >= K0T_K1_THRESHOLDS["semantic_call_avoidance_min"],
        "uncovered_pair_directions_balanced": coverage[
            "semantic_pair_direction_by_coverage"
        ]["parser_uncovered"]
        == {
            "policy_fixed_state_changed": 8,
            "state_fixed_policy_changed": 8,
        },
        "family_action_nondeterministic": all(
            len(actions) >= 4 for actions in coverage["family_actions"].values()
        ),
        "phenomenon_action_nondeterministic": all(
            len(actions) >= 4
            for actions in coverage["phenomenon_actions"].values()
        ),
        "action_paraphrase_balanced": phrase_audit["balanced"],
        "shortcut_headroom": audit["headroom_survives"],
        "unsafe_terminal": metrics["unsafe_terminal"]
        <= K0T_K1_THRESHOLDS["unsafe_terminal_max"],
    }
    readiness = {
        "schema_version": "q5-k0t-k1-readiness-v1",
        "checks": checks,
        "action_phrase_audit": phrase_audit,
        "valid": all(checks.values()),
        "decision": (
            "approved_for_separate_k1_real_model_evaluation"
            if all(checks.values())
            else "blocked_and_boundary_required"
        ),
        "external_requests": 0,
        "model_requests": 0,
    }
    if not readiness["valid"]:
        raise ValueError("K0T shortcut audit breached a preregistered K1 threshold")
    source_hashes = {
        item.name: _sha(item.read_bytes()) for item in sorted(source.iterdir()) if item.is_file()
    }
    lineage = _lineage_receipt(source_hashes)
    report = _report(audit, readiness)
    raw = {
        "shortcut_audit.json": _json_bytes(audit),
        "k1_readiness.json": _json_bytes(readiness),
        "attack_report.md": report.encode(),
        "source_dataset_hashes.json": _json_bytes(
            {
                "schema_version": "q5-k0t-source-dataset-hashes-v1",
                "artifacts": source_hashes,
            }
        ),
        "lineage_receipt.json": _json_bytes(lineage),
    }
    raw["audit_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-k0t-audit-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def _action_phrase_audit(runtime_rows, topology_rows):
    runtime = {row["runtime_ref"]: row for row in runtime_rows}
    semantic = {
        row["runtime_ref"]: row
        for row in topology_rows
        if row["capability_class"] == "semantic_open"
    }
    action_counts: Counter[str] = Counter()
    phrase_counts: Counter[str] = Counter()
    action_families: dict[str, set[str]] = defaultdict(set)
    action_phenomena: dict[str, set[str]] = defaultdict(set)
    for ref, top in semantic.items():
        text = runtime[ref]["policy_text"]
        for action, phrases in K0T_ACTION_PHRASES.items():
            for phrase in phrases:
                if phrase in text:
                    action_counts[action.value] += 1
                    phrase_counts[phrase] += 1
                    action_families[action.value].add(top["policy_family"])
                    action_phenomena[action.value].add(top["semantic_phenomenon"])
    balanced = (
        len(action_counts) == 4
        and FrontierDisposition.human_review.value not in action_counts
        and set(action_counts.values()) == {32}
        and len(phrase_counts) == 16
        and set(phrase_counts.values()) == {8}
        and all(len(values) == 4 for values in action_families.values())
        and all(len(values) == 4 for values in action_phenomena.values())
    )
    return {
        "observed_phrase_count": len(phrase_counts),
        "action_occurrence_counts": dict(action_counts),
        "phrase_occurrence_counts": dict(sorted(phrase_counts.items())),
        "families_per_action": {
            action: sorted(values) for action, values in action_families.items()
        },
        "phenomena_per_action": {
            action: sorted(values) for action, values in action_phenomena.items()
        },
        "balanced": balanced,
    }


def write_k0t_attack_audit(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"K0T audit output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_k0t_attack_audit()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["k1_readiness.json"])


def verify_k0t_attack_audit(
    output_dir: Path | str,
    *,
    require_parent_commit: bool = False,
) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != AUDIT_FILES:
        raise ValueError("K0T audit artifact closure mismatch")
    expected = build_k0t_attack_audit()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"K0T attack audit recomputation mismatch: {name}")
    lineage = json.loads(expected["lineage_receipt.json"])
    if require_parent_commit and _git("rev-parse", "HEAD^") != K0T_DATA_COMMIT:
        raise ValueError("K0T-C parent is not K0T-B")
    if require_parent_commit:
        for path, identity in lineage["frozen_attack_sources"].items():
            if _git("rev-parse", f"HEAD:{path}") != identity["git_blob_sha"]:
                raise ValueError(f"K0T-C changed frozen attack source: {path}")
    return json.loads(expected["k1_readiness.json"])


def _lineage_receipt(source_hashes):
    frozen = {
        path: {
            "git_blob_sha": _git("rev-parse", f"{K0T_DATA_COMMIT}:{path}"),
            "source_sha256": _sha((_root() / path).read_bytes()),
        }
        for path in FROZEN_K0T_SOURCES
    }
    return {
        "schema_version": "q5-k0t-audit-lineage-v1",
        "prereg_commit": "139378c62534660b2a50d771ef6d2c010b00cb62",
        "data_commit": K0T_DATA_COMMIT,
        "expected_audit_parent": K0T_DATA_COMMIT,
        "frozen_attack_sources": frozen,
        "source_dataset_hashes_sha256": _hash_payload(source_hashes),
        "external_requests": 0,
        "model_requests": 0,
    }


def _report(audit, readiness):
    rows = [
        "| Attack | Success | Rate | Threshold | Breached |",
        "|---|---:|---:|---:|---|",
    ]
    rows.extend(
        f"| {item['name']} | {item['success_count']}/{item['evaluated_count']} | "
        f"{item['success_rate']:.2f} | {item['threshold']:.2f} | "
        f"{str(item['breached']).lower()} |"
        for item in audit["attacks"]
    )
    return (
        "# K0T-C Shortcut Attack Audit\n\n"
        + "\n".join(rows)
        + "\n\nK1 readiness: "
        + ("PASS" if readiness["valid"] else "FAIL")
        + ". This audit authorizes only a separate future evaluation; it performs no model calls.\n"
    )


def _root():
    return Path(__file__).resolve().parents[2]


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=_root(), check=True, capture_output=True, text=True
    ).stdout.strip()


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _json_bytes(payload):
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _hash_payload(payload):
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()
