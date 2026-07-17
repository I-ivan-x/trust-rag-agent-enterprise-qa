"""Hash-closed K0U-B preregistration and source-complexity attestation."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any

from app.eval.q5_frontier_k0t_contract import K0T_ACTION_PHRASES
from app.eval.q5_frontier_k0u_contract import (
    K0U_CALL_PROTOCOL,
    K0U_DATA_CONSTRAINTS,
    K0U_K1_GATES,
    K0U_POSTHOC_BOUNDARY_RULE,
    PRACTICAL_COMPLEXITY_BUDGET,
    PRACTICAL_FRONTIER_RULES,
)
from app.eval.q5_frontier_k0u_prereg_parser import preregistered_practical_parser

FROZEN_K0U_SOURCES = (
    "app/schemas/q5_frontier_v6.py",
    "app/eval/q5_frontier_k0u_contract.py",
    "app/eval/q5_frontier_k0u_prereg_parser.py",
    "app/eval/q5_frontier_k0u_prereg.py",
)
K0U_PREREG_FILES = frozenset(
    {
        "frontier_contract.json",
        "complexity_budget.json",
        "complexity_attestation.json",
        "data_constraints.json",
        "call_protocol.json",
        "posthoc_boundary_rule.json",
        "k1_gates.json",
        "source_inventory.json",
        "prereg_hashes.json",
    }
)


def parser_complexity_attestation() -> dict[str, Any]:
    source = inspect.getsource(preregistered_practical_parser)
    module_path = _project_path("app/eval/q5_frontier_k0u_prereg_parser.py")
    module_source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(module_source)
    branch_nodes = sum(
        isinstance(node, (ast.If, ast.IfExp, ast.For, ast.While, ast.BoolOp))
        for node in ast.walk(tree)
    )
    regex_count = len(re.findall(r"re\.(?:compile|findall|fullmatch|search)\(", module_source))
    nonblank = sum(bool(line.strip()) for line in module_source.splitlines())
    lexicon_count = sum(len(values) for values in K0T_ACTION_PHRASES.values())
    forbidden_tokens = ("case_id", "renderer_id", "gold", "policy_ir", "topology")
    forbidden_found = [token for token in forbidden_tokens if token in module_source.lower()]
    long_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and len(node.value) > PRACTICAL_COMPLEXITY_BUDGET["exact_policy_literal_length_max"]
    ]
    checks = {
        "source_lines": nonblank <= PRACTICAL_COMPLEXITY_BUDGET["source_nonblank_lines_max"],
        "regex_count": regex_count <= PRACTICAL_COMPLEXITY_BUDGET["regex_pattern_count_max"],
        "branch_count": branch_nodes
        <= PRACTICAL_COMPLEXITY_BUDGET["ast_branch_node_count_max"],
        "lexicon_count": lexicon_count
        <= PRACTICAL_COMPLEXITY_BUDGET["action_lexicon_entry_count_max"],
        "forbidden_inputs_absent": not forbidden_found,
        "exact_policy_table_absent": not long_literals,
        "runtime_signature_closed": list(
            inspect.signature(preregistered_practical_parser).parameters
        )
        == ["runtime"],
    }
    return {
        "schema_version": "q5-practical-parser-complexity-v1",
        "measurements": {
            "source_nonblank_lines": nonblank,
            "regex_pattern_count": regex_count,
            "ast_branch_node_count": branch_nodes,
            "action_lexicon_entry_count": lexicon_count,
            "forbidden_tokens_found": forbidden_found,
            "long_literal_count": len(long_literals),
            "parser_function_sha256": _sha(source.encode()),
        },
        "checks": checks,
        "valid": all(checks.values()),
    }


def build_k0u_preregistration() -> dict[str, bytes]:
    attestation = parser_complexity_attestation()
    if not attestation["valid"]:
        raise ValueError("K0U practical parser exceeds preregistered complexity budget")
    raw = {
        "frontier_contract.json": _json_bytes(
            {"schema_version": "q5-practical-frontier-contract-v1", **PRACTICAL_FRONTIER_RULES}
        ),
        "complexity_budget.json": _json_bytes(
            {"schema_version": "q5-practical-complexity-budget-v1", **PRACTICAL_COMPLEXITY_BUDGET}
        ),
        "complexity_attestation.json": _json_bytes(attestation),
        "data_constraints.json": _json_bytes(
            {"schema_version": "q5-k0u-data-constraints-v1", **K0U_DATA_CONSTRAINTS}
        ),
        "call_protocol.json": _json_bytes(
            {"schema_version": "q5-k0u-call-protocol-v1", **K0U_CALL_PROTOCOL}
        ),
        "posthoc_boundary_rule.json": _json_bytes(
            {"schema_version": "q5-k0u-posthoc-boundary-v1", **K0U_POSTHOC_BOUNDARY_RULE}
        ),
        "k1_gates.json": _json_bytes(
            {"schema_version": "q5-k0u-k1-gates-v1", **K0U_K1_GATES}
        ),
        "source_inventory.json": _json_bytes(
            {
                "schema_version": "q5-k0u-source-inventory-v1",
                "files": {
                    path: _sha(_project_path(path).read_bytes()) for path in FROZEN_K0U_SOURCES
                },
            }
        ),
    }
    raw["prereg_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-k0u-prereg-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_k0u_preregistration(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"K0U prereg output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_k0u_preregistration()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["complexity_attestation.json"])


def verify_k0u_preregistration(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != K0U_PREREG_FILES:
        raise ValueError("K0U prereg artifact closure mismatch")
    expected = build_k0u_preregistration()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"K0U prereg recomputation mismatch: {name}")
    return json.loads(expected["complexity_attestation.json"])


def _project_path(path: str) -> Path:
    return Path(__file__).resolve().parents[2] / path


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
