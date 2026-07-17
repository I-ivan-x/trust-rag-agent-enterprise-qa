"""K0U-D dual-layer deterministic audit and fail-closed Boundary F."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.eval.q5_boundary_e import runtime_compositional_challenger_k0u
from app.eval.q5_frontier_k0u_contract import (
    K0U_K1_GATES,
    K0U_POSTHOC_BOUNDARY_RULE,
    PRACTICAL_COMPLEXITY_BUDGET,
)
from app.eval.q5_frontier_k0u_dev import _practical, verify_k0u_dev
from app.eval.q5_frontier_k0u_posthoc import (
    _ACTION_CUES,
    independent_runtime_challenger,
)
from app.eval.q5_frontier_k0u_prereg import FROZEN_K0U_SOURCES
from app.eval.q5_frontier_k0u_prereg_parser import preregistered_practical_parser
from app.schemas.q5_frontier_v6 import PracticalParserResult

K0U_DATA_COMMIT = "d86003b82d8e5145bbdc0d63840e7c208072415c"
K0U_PREREG_COMMIT = "b11c97c52d95075b177baee42c0466f6639761fb"
POSTHOC_SOURCE = "app/eval/q5_frontier_k0u_posthoc.py"
K0U_AUDIT_FILES = frozenset(
    {
        "audit_rows.jsonl",
        "attack_metrics.json",
        "posthoc_complexity.json",
        "lineage_receipt.json",
        "boundary_f_summary.json",
        "k1_readiness.json",
        "audit_report.md",
        "audit_hashes.json",
    }
)


def build_k0u_audit(
    dev_dir: Path | str = Path("data/q5_frontier/dev-k0u"),
) -> dict[str, bytes]:
    source = Path(dev_dir)
    verify_k0u_dev(source)
    runtime = {row["runtime_ref"]: row for row in _jsonl(source / "runtime_cases.jsonl")}
    topology = {row["runtime_ref"]: row for row in _jsonl(source / "topology.jsonl")}
    labels = {row["runtime_ref"]: row["disposition"] for row in _jsonl(source / "gold.jsonl")}
    refs = [ref for ref, row in topology.items() if row["capability_class"] == "semantic_open"]
    parsers: tuple[tuple[str, str, Callable[[dict[str, Any]], PracticalParserResult]], ...] = (
        ("preregistered_practical_parser", "preregistered", _run_preregistered),
        ("boundary_e_runtime_compositional", "preregistered", _run_boundary_e),
        ("independent_runtime_challenger", "posthoc", _run_posthoc),
    )
    rows = []
    for name, phase, parser in parsers:
        for ref in refs:
            result = parser(runtime[ref])
            prediction = result.disposition.value if result.disposition else None
            rows.append(
                {
                    "parser": name,
                    "phase": phase,
                    "runtime_ref": ref,
                    "semantic_coverage": topology[ref]["semantic_coverage"],
                    "parser_status": result.status,
                    "prediction": prediction,
                    "correct": prediction == labels[ref],
                    "external_requests": 0,
                    "model_requests": 0,
                }
            )
    metrics = _score(rows)
    posthoc_uncovered = metrics["parsers"]["independent_runtime_challenger"]["parser_uncovered"]
    boundary_triggered = (
        posthoc_uncovered["coverage"] >= K0U_POSTHOC_BOUNDARY_RULE["uncovered_coverage_min"]
        and posthoc_uncovered["conditional_accuracy"]
        == K0U_POSTHOC_BOUNDARY_RULE["conditional_accuracy_required"]
        and posthoc_uncovered["conditional_risk"]
        == K0U_POSTHOC_BOUNDARY_RULE["conditional_risk_required"]
    )
    residual = posthoc_uncovered["abstention_count"]
    preaudit = json.loads((source / "metric_report.json").read_text(encoding="utf-8"))
    blockers = []
    if boundary_triggered:
        blockers.append("posthoc_practical_frontier_breached")
    if residual < K0U_K1_GATES["oracle_resolvable_abstentions_min"]:
        blockers.append("oracle_resolvable_abstentions_below_minimum")
    if (
        preaudit["hybrid_theoretical_call_avoidance"]
        < K0U_K1_GATES["hybrid_theoretical_call_avoidance_min"]
    ):
        blockers.append("hybrid_call_avoidance_below_minimum")
    if preaudit["unsafe_terminal"] > K0U_K1_GATES["unsafe_terminal_max"]:
        blockers.append("unsafe_terminal_detected")
    readiness = {
        "schema_version": "q5-k0u-k1-readiness-v1",
        "valid": not blockers,
        "blockers": blockers,
        "oracle_resolvable_abstentions": residual,
        "hybrid_theoretical_call_avoidance": preaudit["hybrid_theoretical_call_avoidance"],
        "posthoc_boundary_triggered": boundary_triggered,
        "k1_approved": False,
        "external_requests": 0,
        "model_requests": 0,
    }
    if readiness["valid"]:
        readiness["k1_approved"] = True
    boundary = {
        "schema_version": "q5-boundary-f-summary-v1",
        "formed": boundary_triggered,
        "trigger_parser": "independent_runtime_challenger",
        "trigger_subset": "parser_uncovered",
        "trigger_metrics": posthoc_uncovered,
        "fixed_conclusion": (
            "K0U handwritten policies remain inside the practical deterministic frontier"
        ),
        "data_commit": K0U_DATA_COMMIT,
        "historical_data_artifacts_modified": False,
        "k1_approved": False,
        "external_requests": 0,
        "model_requests": 0,
    }
    if not boundary_triggered:
        raise ValueError("K0U audit expected the observed Boundary F trigger")
    complexity = posthoc_complexity_attestation()
    if not complexity["valid"]:
        raise ValueError("post-hoc challenger exceeds the practical complexity budget")
    lineage = _lineage_receipt(source)
    raw = {
        "audit_rows.jsonl": _jsonl_bytes(rows),
        "attack_metrics.json": _json_bytes(metrics),
        "posthoc_complexity.json": _json_bytes(complexity),
        "lineage_receipt.json": _json_bytes(lineage),
        "boundary_f_summary.json": _json_bytes(boundary),
        "k1_readiness.json": _json_bytes(readiness),
        "audit_report.md": _report(metrics, boundary, readiness).encode(),
    }
    raw["audit_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-k0u-audit-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_k0u_audit(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"K0U audit output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_k0u_audit()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["k1_readiness.json"])


def verify_k0u_audit(
    output_dir: Path | str,
    *,
    require_commit_lineage: bool = False,
) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != K0U_AUDIT_FILES:
        raise ValueError("K0U audit artifact closure mismatch")
    expected = build_k0u_audit()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"K0U audit recomputation mismatch: {name}")
    if require_commit_lineage:
        if _git("rev-parse", "HEAD^") != K0U_DATA_COMMIT:
            raise ValueError("K0U-D parent is not the sealed K0U data commit")
        if _git("rev-parse", f"HEAD:{POSTHOC_SOURCE}") != _git_blob(POSTHOC_SOURCE):
            raise ValueError("committed post-hoc source does not match the audit")
    return json.loads(expected["k1_readiness.json"])


def posthoc_complexity_attestation() -> dict[str, Any]:
    path = _root() / POSTHOC_SOURCE
    module_source = path.read_text(encoding="utf-8")
    tree = ast.parse(module_source)
    measurements = {
        "source_nonblank_lines": sum(bool(line.strip()) for line in module_source.splitlines()),
        "regex_pattern_count": len(re.findall(r"re\.compile\(", module_source)),
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
        "source_sha256": _sha(path.read_bytes()),
        "function_sha256": _sha(inspect.getsource(independent_runtime_challenger).encode()),
    }
    forbidden = ("case_id", "renderer_id", "gold", "policy_ir", "topology")
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
        "forbidden_inputs_absent": not any(token in module_source.lower() for token in forbidden),
        "closed_runtime_signature": list(
            inspect.signature(independent_runtime_challenger).parameters
        )
        == ["runtime"],
    }
    return {
        "schema_version": "q5-k0u-posthoc-complexity-v1",
        "measurements": measurements,
        "checks": checks,
        "valid": all(checks.values()),
    }


def _score(rows):
    parser_names = sorted({row["parser"] for row in rows})
    result = {}
    for parser in parser_names:
        result[parser] = {}
        for subset in ("parser_covered", "parser_uncovered", "semantic_overall"):
            selected = [
                row
                for row in rows
                if row["parser"] == parser
                and (subset == "semantic_overall" or row["semantic_coverage"] == subset)
            ]
            parsed = [row for row in selected if row["prediction"] is not None]
            correct = sum(row["correct"] for row in parsed)
            result[parser][subset] = {
                "case_count": len(selected),
                "parsed_count": len(parsed),
                "correct_count": correct,
                "coverage": len(parsed) / len(selected),
                "conditional_accuracy": correct / len(parsed) if parsed else None,
                "conditional_risk": (len(parsed) - correct) / len(parsed) if parsed else None,
                "overall_accuracy": correct / len(selected),
                "abstention_count": len(selected) - len(parsed),
            }
    return {
        "schema_version": "q5-k0u-dual-attack-metrics-v1",
        "parsers": result,
        "external_requests": 0,
        "model_requests": 0,
    }


def _lineage_receipt(dev_dir):
    absent = (
        subprocess.run(
            ["git", "cat-file", "-e", f"{K0U_DATA_COMMIT}:{POSTHOC_SOURCE}"],
            cwd=_root(),
            capture_output=True,
        ).returncode
        != 0
    )
    if not absent:
        raise ValueError("post-hoc challenger was present in the data commit")
    data_files = {
        item.name: _sha(item.read_bytes()) for item in sorted(dev_dir.iterdir()) if item.is_file()
    }
    frozen = {}
    for path in FROZEN_K0U_SOURCES:
        current = (_root() / path).read_bytes()
        committed = subprocess.run(
            ["git", "show", f"{K0U_PREREG_COMMIT}:{path}"],
            cwd=_root(),
            check=True,
            capture_output=True,
        ).stdout
        if current != committed:
            raise ValueError(f"K0U-D changed preregistered source: {path}")
        frozen[path] = {"source_sha256": _sha(current), "git_blob_sha": _git_blob(path)}
    return {
        "schema_version": "q5-k0u-audit-lineage-v1",
        "prereg_commit": K0U_PREREG_COMMIT,
        "data_commit": K0U_DATA_COMMIT,
        "posthoc_source": POSTHOC_SOURCE,
        "posthoc_absent_at_data_commit": absent,
        "posthoc_source_sha256": _sha((_root() / POSTHOC_SOURCE).read_bytes()),
        "frozen_prereg_sources": frozen,
        "sealed_data_artifact_hashes": data_files,
        "external_requests": 0,
        "model_requests": 0,
    }


def _run_preregistered(raw):
    return preregistered_practical_parser(_practical(raw))


def _run_boundary_e(raw):
    state = raw["trusted_observation"]["state"]
    disposition = runtime_compositional_challenger_k0u(raw["policy_text"], state["status"])
    return PracticalParserResult(
        status="complete" if disposition else "abstain",
        reason="pre-data Boundary E grammar" if disposition else "grammar did not match",
        disposition=disposition,
    )


def _run_posthoc(raw):
    return independent_runtime_challenger(_practical(raw))


def _report(metrics, boundary, readiness):
    uncovered = metrics["parsers"][boundary["trigger_parser"]]["parser_uncovered"]
    return (
        "# K0U-D dual-layer deterministic audit\n\n"
        "Preregistered attacks and a source-independent post-hoc runtime challenger were "
        "scored separately on parser-uncovered cases.\n\n"
        f"The post-hoc challenger parsed {uncovered['parsed_count']}/{uncovered['case_count']} "
        f"with conditional accuracy {uncovered['conditional_accuracy']:.6f} and conditional "
        f"risk {uncovered['conditional_risk']:.6f}. Boundary F therefore formed.\n\n"
        f"K1 readiness: `{str(readiness['valid']).lower()}`. Blockers: "
        f"{', '.join(readiness['blockers'])}. No model or external request was made.\n"
    )


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _root():
    return Path(__file__).resolve().parents[2]


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=_root(), check=True, capture_output=True, text=True
    ).stdout.strip()


def _git_blob(path):
    return _git("hash-object", path)


def _json_bytes(payload):
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _jsonl_bytes(rows):
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode()


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()
