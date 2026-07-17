"""Hash-closed Boundary F addendum for the frozen K0U parser-uncovered scope."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from app.eval.q5_boundary_f_addendum_parser import (
    _ACTION_CUES,
    independent_runtime_challenger_v2,
)
from app.eval.q5_frontier_k0u_contract import PRACTICAL_COMPLEXITY_BUDGET
from app.eval.q5_frontier_k0u_dev import _practical, verify_k0u_dev

BASE_HEAD = "17c6c7ddf641fc6b8e5c803f35743fd369f8b258"
DATA_COMMIT = "d86003b82d8e5145bbdc0d63840e7c208072415c"
PARSER_SOURCE = "app/eval/q5_boundary_f_addendum_parser.py"
DEV_ROOT = Path("data/q5_frontier/dev-k0u")
OLD_AUDIT_ROOT = Path("data/q5_frontier/dev-k0u-audit")
SOURCE_HASHES = {
    "data/q5_frontier/dev-k0u/runtime_cases.jsonl": (
        "ecebb9983d310506ae59c1253654fef801dc3fecf714fbeeed2af86a03e39bd0"
    ),
    "data/q5_frontier/dev-k0u/topology.jsonl": (
        "3c6fc4724d6b161b6daf3efe2b1c3d5ed2f24859bbcaafc808f9c10b8b3b7370"
    ),
    "data/q5_frontier/dev-k0u/gold.jsonl": (
        "1616e1789872a4d0c5f9bd219f1b47930f8f2ccfad91b949aaea577f48430165"
    ),
    "data/q5_frontier/dev-k0u/artifact_hashes.json": (
        "0f3573568ef052a8fe755a5d4bb9a771484b4f2954a713f6a7737a346062ae07"
    ),
    "data/q5_frontier/dev-k0u-audit/boundary_f_summary.json": (
        "a10d4cbff6fa9c7d554a87ad06dc63e79db235d289190d72af9addf0d6d97648"
    ),
    "data/q5_frontier/dev-k0u-audit/audit_hashes.json": (
        "28fda1e4174efdbbd20a8eece796e95363bec87275dca7e9b238b4f51846882a"
    ),
}
ADDENDUM_FILES = frozenset(
    {
        "addendum_rows.jsonl",
        "addendum_metrics.json",
        "frozen_scope.json",
        "lineage_receipt.json",
        "parser_attestation.json",
        "addendum_report.md",
        "artifact_hashes.json",
    }
)


def build_boundary_f_addendum() -> dict[str, bytes]:
    _verify_frozen_sources()
    verify_k0u_dev(DEV_ROOT)
    runtime = {row["runtime_ref"]: row for row in _jsonl(DEV_ROOT / "runtime_cases.jsonl")}
    topology = {row["runtime_ref"]: row for row in _jsonl(DEV_ROOT / "topology.jsonl")}
    labels = {row["runtime_ref"]: row["disposition"] for row in _jsonl(DEV_ROOT / "gold.jsonl")}
    refs = sorted(
        ref
        for ref, row in topology.items()
        if row["capability_class"] == "semantic_open"
        and row["semantic_coverage"] == "parser_uncovered"
    )
    if len(refs) != 32 or len(refs) != len(set(refs)):
        raise ValueError("Boundary F addendum requires 32 unique frozen runtime refs")
    rows = []
    for ref in refs:
        result = independent_runtime_challenger_v2(_practical(runtime[ref]))
        prediction = result.disposition.value if result.disposition else None
        rows.append(
            {
                "runtime_ref": ref,
                "parser_status": result.status,
                "prediction": prediction,
                "gold_disposition": labels[ref],
                "correct": prediction == labels[ref],
                "model_requests": 0,
                "external_requests": 0,
            }
        )
    metrics = _metrics(rows)
    _enforce_metrics(metrics)
    attestation = parser_complexity_attestation_v2()
    if not attestation["valid"]:
        raise ValueError("Boundary F addendum parser exceeds the frozen complexity budget")
    scope = {
        "schema_version": "q5-boundary-f-addendum-scope-v1",
        "claim_scope": "frozen K0U parser-uncovered 32-case scope",
        "runtime_refs": refs,
        "runtime_ref_count": len(refs),
        "runtime_refs_sha256": _sha(_jsonl_bytes([{"runtime_ref": ref} for ref in refs])),
        "source_artifact_sha256": SOURCE_HASHES,
        "model_requests": 0,
        "external_requests": 0,
    }
    lineage = {
        "schema_version": "q5-boundary-f-addendum-lineage-v1",
        "implementation_base_head": BASE_HEAD,
        "data_commit": DATA_COMMIT,
        "original_boundary_f_summary_sha256": SOURCE_HASHES[
            "data/q5_frontier/dev-k0u-audit/boundary_f_summary.json"
        ],
        "original_boundary_f_audit_hashes_sha256": SOURCE_HASHES[
            "data/q5_frontier/dev-k0u-audit/audit_hashes.json"
        ],
        "parser_source": PARSER_SOURCE,
        "parser_source_sha256": attestation["measurements"]["source_sha256"],
        "parser_function_sha256": attestation["measurements"]["function_sha256"],
        "original_boundary_f_artifacts_modified": False,
        "model_requests": 0,
        "external_requests": 0,
    }
    raw = {
        "addendum_rows.jsonl": _jsonl_bytes(rows),
        "addendum_metrics.json": _json_bytes(metrics),
        "frozen_scope.json": _json_bytes(scope),
        "lineage_receipt.json": _json_bytes(lineage),
        "parser_attestation.json": _json_bytes(attestation),
        "addendum_report.md": _report(metrics).encode(),
    }
    raw["artifact_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-boundary-f-addendum-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_boundary_f_addendum(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Boundary F addendum output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_boundary_f_addendum()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["addendum_metrics.json"])


def verify_boundary_f_addendum(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    actual_files = {item.name for item in target.iterdir() if item.is_file()}
    if actual_files != ADDENDUM_FILES:
        raise ValueError("Boundary F addendum artifact closure mismatch")
    stored_hashes = json.loads((target / "artifact_hashes.json").read_text(encoding="utf-8"))
    expected_hashed_files = ADDENDUM_FILES - {"artifact_hashes.json"}
    if set(stored_hashes.get("artifacts", {})) != expected_hashed_files:
        raise ValueError("Boundary F addendum canonical hash inventory mismatch")
    for name in expected_hashed_files:
        if stored_hashes["artifacts"][name] != _sha((target / name).read_bytes()):
            raise ValueError(f"Boundary F addendum artifact hash mismatch: {name}")
    rows = _jsonl(target / "addendum_rows.jsonl")
    scope = json.loads((target / "frozen_scope.json").read_text(encoding="utf-8"))
    row_refs = [row.get("runtime_ref") for row in rows]
    scope_refs = scope.get("runtime_refs", [])
    if len(rows) != 32 or len(row_refs) != len(set(row_refs)):
        raise ValueError("Boundary F addendum rows contain duplicate or missing trials")
    if row_refs != scope_refs or len(scope_refs) != 32 or len(scope_refs) != len(set(scope_refs)):
        raise ValueError("Boundary F addendum frozen case set mismatch")
    expected = build_boundary_f_addendum()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"Boundary F addendum recomputation mismatch: {name}")
    return json.loads(expected["addendum_metrics.json"])


def parser_complexity_attestation_v2() -> dict[str, Any]:
    path = _root() / PARSER_SOURCE
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = (
        "case_id",
        "runtime_ref",
        "semantic_coverage",
        "renderer_id",
        "gold",
        "policy_ir",
        "authoring",
        "topology",
    )
    case_specific_literals = ("r067", "r068", "signal_327")
    measurements = {
        "source_nonblank_lines": sum(bool(line.strip()) for line in source.splitlines()),
        "regex_pattern_count": len(re.findall(r"re\.compile\(", source)),
        "ast_branch_node_count": sum(
            isinstance(node, (ast.If, ast.IfExp, ast.For, ast.While, ast.BoolOp))
            for node in ast.walk(tree)
        ),
        "action_lexicon_entry_count": len(_ACTION_CUES),
        "long_literal_count": sum(
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and len(node.value) > PRACTICAL_COMPLEXITY_BUDGET["exact_policy_literal_length_max"]
            for node in ast.walk(tree)
        ),
        "forbidden_tokens_found": [token for token in forbidden if token in source.lower()],
        "case_specific_literals_found": [
            token for token in case_specific_literals if token in source.lower()
        ],
        "source_sha256": _sha(path.read_bytes()),
        "function_sha256": _sha(inspect.getsource(independent_runtime_challenger_v2).encode()),
    }
    checks = {
        "source_lines": measurements["source_nonblank_lines"]
        <= PRACTICAL_COMPLEXITY_BUDGET["source_nonblank_lines_max"],
        "regex_count": measurements["regex_pattern_count"]
        <= PRACTICAL_COMPLEXITY_BUDGET["regex_pattern_count_max"],
        "branch_count": measurements["ast_branch_node_count"]
        <= PRACTICAL_COMPLEXITY_BUDGET["ast_branch_node_count_max"],
        "lexicon_count": measurements["action_lexicon_entry_count"]
        <= PRACTICAL_COMPLEXITY_BUDGET["action_lexicon_entry_count_max"],
        "exact_policy_table_absent": measurements["long_literal_count"] == 0,
        "forbidden_inputs_absent": not measurements["forbidden_tokens_found"],
        "case_specific_lookup_absent": not measurements["case_specific_literals_found"],
        "closed_runtime_signature": list(
            inspect.signature(independent_runtime_challenger_v2).parameters
        )
        == ["runtime"],
    }
    return {
        "schema_version": "q5-boundary-f-addendum-parser-attestation-v1",
        "measurements": measurements,
        "checks": checks,
        "valid": all(checks.values()),
    }


def _metrics(rows):
    parsed = [row for row in rows if row["prediction"] is not None]
    correct = sum(row["correct"] for row in parsed)
    total = len(rows)
    return {
        "schema_version": "q5-boundary-f-addendum-metrics-v1",
        "claim_scope": "frozen K0U parser-uncovered 32-case scope",
        "case_count": total,
        "parsed_count": len(parsed),
        "correct_count": correct,
        "coverage": len(parsed) / total,
        "conditional_accuracy": correct / len(parsed) if parsed else None,
        "conditional_risk": (len(parsed) - correct) / len(parsed) if parsed else None,
        "abstention_count": total - len(parsed),
        "previously_uncovered_cases_resolved": {"resolved": len(parsed), "total": total},
        "remaining_uncovered_cases": {"count": total - len(parsed), "total": total},
        "controlled_prose_track": "closed",
        "k1_approved": False,
        "boundary_g_allowed": False,
        "new_k1_data_allowed": False,
        "model_requests": 0,
        "external_requests": 0,
    }


def _enforce_metrics(metrics):
    expected = {
        "case_count": 32,
        "parsed_count": 32,
        "correct_count": 32,
        "coverage": 1.0,
        "conditional_accuracy": 1.0,
        "conditional_risk": 0.0,
        "abstention_count": 0,
        "previously_uncovered_cases_resolved": {"resolved": 32, "total": 32},
        "remaining_uncovered_cases": {"count": 0, "total": 32},
        "controlled_prose_track": "closed",
        "k1_approved": False,
        "boundary_g_allowed": False,
        "new_k1_data_allowed": False,
    }
    if any(metrics[key] != value for key, value in expected.items()):
        raise ValueError("Boundary F addendum exact frozen-scope metrics failed")


def _verify_frozen_sources():
    current_head = _git("rev-parse", "HEAD")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_HEAD, current_head],
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestry.returncode != 0:
        raise ValueError("Boundary F addendum base HEAD is not an ancestor of current HEAD")
    for path, expected in SOURCE_HASHES.items():
        actual = _sha((_root() / path).read_bytes())
        if actual != expected:
            raise ValueError(f"Boundary F addendum frozen source changed: {path}")


def _report(metrics):
    return (
        "# Boundary F addendum evidence\n\n"
        f"Claim scope: {metrics['claim_scope']}.\n\n"
        f"Within that frozen scope, the versioned parser produced {metrics['parsed_count']} "
        f"parsed and {metrics['correct_count']} correct decisions from "
        f"{metrics['case_count']} cases. Coverage is {metrics['coverage']:.6f}; conditional "
        f"accuracy is {metrics['conditional_accuracy']:.6f}; conditional risk within the "
        f"named frozen scope is {metrics['conditional_risk']:.6f}.\n\n"
        "This closes only the controlled-prose track. It does not authorize K1, Boundary G, "
        "new K1 data, or any open-world LLM-value claim.\n"
    )


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


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
