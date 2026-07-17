"""Hash-closed post-hoc deterministic Boundary C over frozen dev-v3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.eval.q5_frontier_parser_suite_v4 import compositional_challenger
from app.eval.q5_frontier_v3 import verify_frontier_v3_artifacts
from app.schemas.q5_frontier_v4 import FrontierRuntimePayloadV4

BOUNDARY_C_FILES = frozenset(
    {
        "boundary_c_summary.json",
        "boundary_c_report.md",
        "frozen_dev_v3_hashes.json",
        "parser_rows.jsonl",
        "boundary_c_hashes.json",
    }
)


def build_boundary_c(
    dev_v3_dir: Path | str = Path("data/q5_frontier/dev-v3"),
) -> dict[str, bytes]:
    source = Path(dev_v3_dir)
    verify_frontier_v3_artifacts(source)
    runtime = {row["runtime_ref"]: row for row in _jsonl(source / "runtime_cases.jsonl")}
    execution = {
        row["runtime_ref"]: row for row in _jsonl(source / "execution_rows.jsonl")
    }
    topology = {row["runtime_ref"]: row for row in _jsonl(source / "topology.jsonl")}
    sealed_ir = {row["runtime_ref"]: row["policy_ir"] for row in _jsonl(source / "policy_ir.jsonl")}
    refs = [
        ref
        for ref, row in topology.items()
        if row["capability_class"] == "semantic_open"
        and execution[ref]["parser_status"] == "abstain"
    ]
    rows = []
    for ref in refs:
        payload = runtime[ref]
        parsed = compositional_challenger(
            FrontierRuntimePayloadV4(
                **{
                    **payload,
                    "runtime_ref": ref.replace(
                        "frontier-v3-resource", "parser-uncovered-dev-resource"
                    ),
                }
            )
        )
        exact = (
            parsed.policy_ir is not None
            and parsed.policy_ir.model_dump(mode="json") == sealed_ir[ref]
        )
        rows.append(
            {
                "runtime_ref": ref,
                "parser_status": parsed.status,
                "parser_reason": parsed.reason,
                "exact_ir_match": exact,
            }
        )
    if len(rows) != 16 or not all(row["exact_ir_match"] for row in rows):
        raise ValueError("Boundary C requires exact post-hoc compositional 16/16")
    frozen = {
        item.name: _sha(item.read_bytes()) for item in sorted(source.iterdir()) if item.is_file()
    }
    summary = {
        "schema_version": "q5-boundary-c-summary-v1",
        "source_namespace": "data/q5_frontier/dev-v3",
        "post_hoc_compositional_abstention_count": 16,
        "post_hoc_compositional_success_count": 16,
        "post_hoc_compositional_success_rate": 1.0,
        "external_requests": 0,
        "model_requests": 0,
        "fixed_conclusion": "当前四类模板仍在 deterministic frontier",
    }
    report = (
        "# Boundary C\n\n"
        "The post-hoc compositional challenger resolves all 16 prior parser "
        "abstentions with exact Policy IR agreement (16/16).\n\n"
        "Fixed conclusion: 当前四类模板仍在 deterministic frontier。\n"
    ).encode()
    raw = {
        "boundary_c_summary.json": _json_bytes(summary),
        "boundary_c_report.md": report,
        "frozen_dev_v3_hashes.json": _json_bytes(
            {
                "schema_version": "q5-boundary-c-frozen-dev-v3-hashes-v1",
                "artifact_count": len(frozen),
                "artifacts": frozen,
            }
        ),
        "parser_rows.jsonl": _jsonl_bytes(rows),
    }
    raw["boundary_c_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-boundary-c-hashes-v1",
            "artifacts": {name: _sha(value) for name, value in sorted(raw.items())},
        }
    )
    return raw


def write_boundary_c(output_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Boundary C output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_boundary_c(**kwargs)
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["boundary_c_summary.json"])


def verify_boundary_c(output_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != BOUNDARY_C_FILES:
        raise ValueError("Boundary C artifact closure mismatch")
    expected = build_boundary_c(**kwargs)
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"Boundary C recomputation mismatch: {name}")
    return json.loads(expected["boundary_c_summary.json"])


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
