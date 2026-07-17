"""Hash-closed Boundary D: K0SR's uncovered slice has a family-label shortcut."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.eval.q5_frontier_attack_suite_v5 import evaluate_shortcut_attacks
from app.eval.q5_frontier_parser_uncovered_v4 import verify_parser_uncovered_dev_v4

BOUNDARY_D_FILES = frozenset(
    {
        "boundary_d_summary.json",
        "boundary_d_report.md",
        "shortcut_audit.json",
        "frozen_k0sr_hashes.json",
        "boundary_d_hashes.json",
    }
)


def build_boundary_d(
    source_dir: Path | str = Path("data/q5_frontier/parser_uncovered_dev"),
) -> dict[str, bytes]:
    source = Path(source_dir)
    verify_parser_uncovered_dev_v4(source)
    runtime = _jsonl(source / "runtime_cases.jsonl")
    topology = _jsonl(source / "topology.jsonl")
    for row in topology:
        row["renderer_id"] = "k0sr-" + row["semantic_phenomenon"]
    gold = _jsonl(source / "gold.jsonl")
    audit = evaluate_shortcut_attacks(runtime, topology, gold).model_dump(mode="json")
    shortcut = next(
        item
        for item in audit["attacks"]
        if item["name"] == "token_pattern_state_equality"
    )
    if shortcut["success_count"] != 16 or shortcut["success_rate"] != 1.0:
        raise ValueError("Boundary D requires the reproduced 16/16 label shortcut")
    frozen = {
        item.name: _sha(item.read_bytes()) for item in sorted(source.iterdir()) if item.is_file()
    }
    summary = {
        "schema_version": "q5-boundary-d-summary-v1",
        "source_namespace": "data/q5_frontier/parser_uncovered_dev",
        "shortcut": "token_pattern_state_equality",
        "semantic_uncovered_count": 16,
        "shortcut_success_count": 16,
        "shortcut_success_rate": 1.0,
        "headroom_invalidated": True,
        "fixed_conclusion": (
            "K0SR parser-uncovered labels are deterministically recoverable from policy "
            "family plus token/state equality and cannot support an LLM-value claim."
        ),
        "external_requests": 0,
        "model_requests": 0,
    }
    raw = {
        "boundary_d_summary.json": _json_bytes(summary),
        "boundary_d_report.md": (
            b"# Boundary D: Label Shortcut\n\n"
            b"A preregistered family plus token/state-equality attack recovers all 16 "
            b"K0SR uncovered labels. The package is a deterministic-frontier "
            b"counterexample, not LLM-value evidence.\n"
        ),
        "shortcut_audit.json": _json_bytes(audit),
        "frozen_k0sr_hashes.json": _json_bytes(
            {
                "schema_version": "q5-boundary-d-frozen-k0sr-hashes-v1",
                "artifacts": frozen,
            }
        ),
    }
    raw["boundary_d_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-boundary-d-hashes-v1",
            "artifacts": {name: _sha(value) for name, value in sorted(raw.items())},
        }
    )
    return raw


def write_boundary_d(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Boundary D output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_boundary_d()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["boundary_d_summary.json"])


def verify_boundary_d(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != BOUNDARY_D_FILES:
        raise ValueError("Boundary D artifact closure mismatch")
    expected = build_boundary_d()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"Boundary D recomputation mismatch: {name}")
    return json.loads(expected["boundary_d_summary.json"])


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
