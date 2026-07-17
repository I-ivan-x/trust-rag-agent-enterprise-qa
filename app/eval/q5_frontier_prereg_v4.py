"""K0SR-A preregistration package built before development authoring exists."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.schemas.q5_frontier_v4 import compact_policy_ir_prompt_contract_v4

FROZEN_SOURCE_PATHS = (
    "app/eval/q5_frontier_parser_suite_v4.py",
    "app/eval/q5_frontier_compiler_v4.py",
    "app/schemas/q5_frontier_v4.py",
    "app/eval/q5_frontier_prereg_v4.py",
)
PREREG_FILES = frozenset(
    {
        "parser_suite_contract.json",
        "prompt_contract.json",
        "metrics_contract.json",
        "thresholds.json",
        "source_inventory.json",
        "prereg_hashes.json",
    }
)


def build_preregistration_v4() -> dict[str, bytes]:
    parser_contract = {
        "schema_version": "q5-deterministic-suite-contract-v4",
        "suite_name": "q5-preregistered-deterministic-suite-v4",
        "components": [
            "structured_parser",
            "boundary_b_parser",
            "compositional_challenger",
            "alias_condition_normalizer",
        ],
        "selector": "best_of_deterministic_selector",
        "selector_conflict_semantics": "ambiguous_fail_closed",
        "runtime_only": True,
        "external_requests": 0,
        "model_requests": 0,
    }
    metrics = {
        "schema_version": "q5-parser-uncovered-headroom-metrics-v1",
        "allowed_report_fields": [
            "oracle_resolvable_abstentions",
            "family_coverage",
            "phenomenon_coverage",
            "deterministic_conditional_risk",
            "call_headroom",
            "token_avoidance",
        ],
        "forbidden_pre_model_fields": [
            "beneficial_evidence",
            "beneficial_capture",
            "model_uplift",
        ],
        "call_protocol": {
            "frozen": True,
            "llm_only": "one semantic parse call for every semantic-open case",
            "hybrid": "one semantic parse call only after best-of suite abstains",
            "retry": 0,
            "fallback": "none",
        },
        "token_avoidance": "not_evaluated",
    }
    thresholds = {
        "schema_version": "q5-parser-uncovered-thresholds-v1",
        "minimum_case_count": 80,
        "minimum_parser_uncovered_case_count": 16,
        "minimum_family_count": 4,
        "minimum_phenomenon_count": 4,
        "maximum_deterministic_conditional_risk": 0.0,
        "require_oracle_resolvable_abstentions": True,
        "headline_value_claim_allowed_before_model_run": False,
    }
    source_inventory = {
        "schema_version": "q5-frontier-prereg-source-inventory-v1",
        "files": {
            path: _sha(_project_path(path).read_bytes()) for path in FROZEN_SOURCE_PATHS
        },
    }
    raw = {
        "parser_suite_contract.json": _json_bytes(parser_contract),
        "prompt_contract.json": _json_bytes(compact_policy_ir_prompt_contract_v4()),
        "metrics_contract.json": _json_bytes(metrics),
        "thresholds.json": _json_bytes(thresholds),
        "source_inventory.json": _json_bytes(source_inventory),
    }
    raw["prereg_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-frontier-prereg-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_preregistration_v4(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"preregistration output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_preregistration_v4()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["parser_suite_contract.json"])


def verify_preregistration_v4(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != PREREG_FILES:
        raise ValueError("preregistration artifact closure mismatch")
    expected = build_preregistration_v4()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"preregistration recomputation mismatch: {name}")
    return json.loads(expected["parser_suite_contract.json"])


def _project_path(path: str) -> Path:
    return Path(__file__).resolve().parents[2] / path


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
