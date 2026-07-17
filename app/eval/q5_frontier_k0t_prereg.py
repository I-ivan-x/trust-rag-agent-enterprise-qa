"""Build the K0T-A preregistration package without development labels or authoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.eval.q5_frontier_k0t_contract import (
    K0T_CALL_PROTOCOL,
    K0T_K1_THRESHOLDS,
    K0T_METRIC_CONTRACT,
    K0T_TOPOLOGY_CONSTRAINTS,
)

FROZEN_K0T_SOURCES = (
    "app/schemas/q5_frontier_v5.py",
    "app/eval/q5_frontier_k0t_contract.py",
    "app/eval/q5_frontier_attack_suite_v5.py",
    "app/eval/q5_frontier_k0t_prereg.py",
)
PREREG_K0T_FILES = frozenset(
    {
        "attack_suite.json",
        "data_constraints.json",
        "metric_contract.json",
        "call_protocol.json",
        "k1_thresholds.json",
        "source_inventory.json",
        "prereg_hashes.json",
    }
)


def build_k0t_preregistration() -> dict[str, bytes]:
    raw = {
        "attack_suite.json": _json_bytes(
            {
                "schema_version": "q5-k0t-attack-suite-v1",
                "attacks": [
                    "family_only",
                    "phenomenon_only",
                    "renderer_template_only",
                    "token_pattern_state_equality",
                    "action_phrase_omitted",
                    "lexical_condition_action_parser",
                    "majority_action",
                    "pair_neighbor",
                ],
                "post_hoc_k0sr_16_of_16_included": True,
                "external_requests": 0,
                "model_requests": 0,
            }
        ),
        "data_constraints.json": _json_bytes(
            {"schema_version": "q5-k0t-data-constraints-v1", **K0T_TOPOLOGY_CONSTRAINTS}
        ),
        "metric_contract.json": _json_bytes(
            {"schema_version": "q5-k0t-metric-contract-v1", **K0T_METRIC_CONTRACT}
        ),
        "call_protocol.json": _json_bytes(
            {"schema_version": "q5-k0t-call-protocol-v1", **K0T_CALL_PROTOCOL}
        ),
        "k1_thresholds.json": _json_bytes(
            {"schema_version": "q5-k0t-k1-thresholds-v1", **K0T_K1_THRESHOLDS}
        ),
        "source_inventory.json": _json_bytes(
            {
                "schema_version": "q5-k0t-prereg-source-inventory-v1",
                "files": {
                    path: _sha(_project_path(path).read_bytes())
                    for path in FROZEN_K0T_SOURCES
                },
            }
        ),
    }
    raw["prereg_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-k0t-prereg-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_k0t_preregistration(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"K0T prereg output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_k0t_preregistration()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["attack_suite.json"])


def verify_k0t_preregistration(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != PREREG_K0T_FILES:
        raise ValueError("K0T prereg artifact closure mismatch")
    expected = build_k0t_preregistration()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"K0T prereg recomputation mismatch: {name}")
    return json.loads(expected["attack_suite.json"])


def _project_path(path: str) -> Path:
    return Path(__file__).resolve().parents[2] / path


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
