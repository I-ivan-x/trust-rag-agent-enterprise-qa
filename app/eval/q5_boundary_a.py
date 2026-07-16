"""Hash-closed Boundary A evidence derived from already verified Q5 artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.eval.q5_provenance import (
    q5_read_json,
    q5_sha256_file,
    verify_q5_graded_run,
)
from app.eval.q5_symbolic_control import verify_q5_strong_symbolic_artifacts
from app.eval.q5_value_ledger import verify_q5_value_ledger
from scripts.preflight_q5_i import verify_q5_i_preflight_receipt

BOUNDARY_A_SUMMARY_SCHEMA = "q5-boundary-a-summary-v1"
BOUNDARY_A_HASHES_SCHEMA = "q5-boundary-a-hashes-v1"
BOUNDARY_A_FILES = frozenset(
    {"boundary_a_summary.json", "boundary_a_report.md", "boundary_a_hashes.json"}
)
_BOUNDARY_SOURCE_FILES = (
    "app/eval/q5_boundary_a.py",
    "app/eval/q5_claim_readiness.py",
    "app/eval/q5_provenance.py",
    "app/eval/q5_symbolic_control.py",
    "app/eval/q5_value_ledger.py",
    "scripts/preflight_q5_i.py",
)


def build_boundary_a_evidence(
    *,
    v3_run: Path | str,
    v3_gold: Path | str,
    v4_run: Path | str,
    v4_gold: Path | str,
    value_dir: Path | str,
    symbolic_dir: Path | str,
    receipt_path: Path | str,
    dataset_root: Path | str,
) -> dict[str, bytes]:
    """Recompute Boundary A solely from verified source artifacts."""

    v3_root = Path(v3_run)
    v4_root = Path(v4_run)
    value_root = Path(value_dir)
    symbolic_root = Path(symbolic_dir)
    receipt = Path(receipt_path)
    dataset = Path(dataset_root)
    verified_v3 = verify_q5_graded_run(v3_root, v3_gold)
    verified_v4 = verify_q5_graded_run(v4_root, v4_gold)
    if verified_v3.protocol_version != "v3" or not verified_v3.real_run:
        raise ValueError("Boundary A requires the verified v3 real run")
    if verified_v4.protocol_version != "v4" or verified_v4.real_run:
        raise ValueError("Boundary A requires a verified v4 non-real run")
    value = verify_q5_value_ledger(v4_root, v4_gold, value_root)
    symbolic = verify_q5_strong_symbolic_artifacts(
        tasks_path=dataset / "tasks.jsonl",
        environment_path=dataset / "environment.jsonl",
        runtime_cases_path=dataset / "runtime_cases.jsonl",
        gold_path=v4_gold,
        output_dir=symbolic_root,
    )
    preflight = verify_q5_i_preflight_receipt(
        receipt,
        mock_run=v4_root,
        gold_path=v4_gold,
        value_dir=value_root,
        symbolic_dir=symbolic_root,
        dataset_root=dataset,
    )
    v3_summary = q5_read_json(v3_root / "summary.json")
    v4_summary = q5_read_json(v4_root / "summary.json")
    v3_hybrid = _system_metrics(v3_summary, "q5_hybrid_agent")
    v4_hybrid = _system_metrics(v4_summary, "q5_hybrid_agent")
    blockers = list(preflight["value_frontier"]["claim_readiness"]["blockers"])
    required_blockers = ["claim_headroom", "beneficial_evidence_absent"]
    if not set(required_blockers) <= set(blockers):
        raise ValueError("Boundary A core claim blockers are missing")
    if value.get("value_class_counts") != {"neutral": 108}:
        raise ValueError("Boundary A expected the verified 108-neutral value ledger")
    summary: dict[str, Any] = {
        "schema_version": BOUNDARY_A_SUMMARY_SCHEMA,
        "boundary": "explicit_closed_vocabulary_fully_parseable_policy_grammar",
        "sources": {
            "v3_deepseek_real": {
                "run_id": verified_v3.run_id,
                "mode": verified_v3.mode,
                "real_run": verified_v3.real_run,
                "mock_used": verified_v3.mock_used,
                "raw_manifest_sha256": verified_v3.raw_manifest_sha256,
            },
            "v4_deterministic_mock": {
                "run_id": verified_v4.run_id,
                "mode": verified_v4.mode,
                "real_run": verified_v4.real_run,
                "mock_used": verified_v4.mock_used,
                "raw_manifest_sha256": verified_v4.raw_manifest_sha256,
            },
            "value_sidecar_schema": value["schema_version"],
            "symbolic_sidecar_schema": symbolic["schema_version"],
            "preflight_schema": preflight["schema_version"],
        },
        "evidence": {
            "v3_real_weak_uplift": {
                "trajectory_qualified_semantic_uplift": v3_summary["comparisons"][
                    "semantic_uplift_hybrid_vs_rule"
                ],
                "bootstrap_ci": v3_summary["comparisons"]["paired_bootstrap_ci"],
                "hybrid_within_policy_pair_success": v3_hybrid[
                    "within_policy_pair_success"
                ],
                "hybrid_cross_policy_pair_success": v3_hybrid[
                    "cross_policy_pair_success"
                ],
                "within_policy_failure_case_ids": v3_hybrid[
                    "within_policy_failure_case_ids"
                ],
                "cross_policy_failure_case_ids": v3_hybrid[
                    "cross_policy_failure_case_ids"
                ],
            },
            "v4_closed_vocabulary_symbolic_control": {
                "semantic_success": symbolic["semantic_success"],
                "within_policy_pair_success": symbolic["within_policy_pair_success"],
                "cross_policy_pair_success": symbolic["cross_policy_pair_success"],
                "control_kind": symbolic["control_kind"],
                "claim_scope": symbolic["claim_scope"],
            },
            "v4_value_ledger": {
                "value_class_counts": value["value_class_counts"],
                "beneficial_group_count": value["beneficial_group_count"],
                "beneficial_capture": value["beneficial_value_capture"],
                "beneficial_capture_vacuous": value["beneficial_capture_vacuous"],
            },
            "v4_hybrid_incremental_value": {
                "llm_calls": v4_hybrid["llm_calls"],
                "value_ledger_llm_calls": value["hybrid_total_llm_calls"],
                "incremental_successes_per_100_calls": value[
                    "incremental_successes_per_100_calls"
                ],
            },
            "claim_readiness": {
                "valid": preflight["value_frontier"]["claim_readiness"]["valid"],
                "core_blockers": required_blockers,
                "all_blockers": blockers,
            },
        },
        "fixed_conclusion": {
            "incremental_llm_value_proven": False,
            "recommended_execution": "deterministic_parser_compiler",
            "llm_behavior": "abstain",
            "statement": (
                "For explicit, closed-vocabulary, fully parseable policy grammar, "
                "incremental LLM value is not proven; execute with a deterministic "
                "parser/compiler and require the LLM to abstain."
            ),
        },
        "scope_limits": {
            "v4_mock_is_real": False,
            "mock_used_for_real_claim": False,
            "general_natural_language_policy_extrapolation": False,
        },
        "source_artifact_sha256": _source_artifact_inventory(
            v3_root, v4_root, value_root, symbolic_root, receipt
        ),
        "source_code_sha256": _source_code_inventory(),
    }
    report = _render_boundary_a_report(summary).encode()
    summary_bytes = _json_bytes(summary)
    raw = {
        "boundary_a_summary.json": summary_bytes,
        "boundary_a_report.md": report,
    }
    raw["boundary_a_hashes.json"] = _json_bytes(
        {
            "schema_version": BOUNDARY_A_HASHES_SCHEMA,
            "artifacts": {
                name: hashlib.sha256(payload).hexdigest()
                for name, payload in sorted(raw.items())
            },
        }
    )
    return raw


def write_boundary_a_evidence(output_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Boundary A output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_boundary_a_evidence(**kwargs)
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["boundary_a_summary.json"])


def verify_boundary_a_evidence(output_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
    target = Path(output_dir)
    actual = {path.name for path in target.iterdir() if path.is_file()}
    if actual != BOUNDARY_A_FILES:
        raise ValueError("Boundary A artifact closure mismatch")
    expected = build_boundary_a_evidence(**kwargs)
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"Boundary A recomputation mismatch: {name}")
    return json.loads(expected["boundary_a_summary.json"])


def _system_metrics(summary: Mapping[str, Any], system: str) -> Mapping[str, Any]:
    systems = summary.get("by_system")
    if not isinstance(systems, Mapping) or not isinstance(systems.get(system), Mapping):
        raise ValueError(f"Boundary A source summary lacks {system}")
    return systems[system]


def _source_artifact_inventory(
    v3: Path,
    v4: Path,
    value: Path,
    symbolic: Path,
    receipt: Path,
) -> dict[str, str]:
    paths = {
        "v3/manifest.json": v3 / "manifest.json",
        "v3/graded_manifest.json": v3 / "graded_manifest.json",
        "v3/summary.json": v3 / "summary.json",
        "v3/graded_rows.jsonl": v3 / "graded_rows.jsonl",
        "v4/manifest.json": v4 / "manifest.json",
        "v4/graded_manifest.json": v4 / "graded_manifest.json",
        "v4/summary.json": v4 / "summary.json",
        "v4/graded_rows.jsonl": v4 / "graded_rows.jsonl",
        "value/value_summary.json": value / "value_summary.json",
        "value/value_ledger.jsonl": value / "value_ledger.jsonl",
        "symbolic/symbolic_summary.json": symbolic / "symbolic_summary.json",
        "symbolic/symbolic_rows.jsonl": symbolic / "symbolic_rows.jsonl",
        "preflight/receipt.json": receipt,
    }
    return {name: q5_sha256_file(path) for name, path in sorted(paths.items())}


def _source_code_inventory() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    return {
        name: _canonical_source_sha256(root / name)
        for name in _BOUNDARY_SOURCE_FILES
    }


def _canonical_source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _render_boundary_a_report(summary: Mapping[str, Any]) -> str:
    evidence = summary["evidence"]
    v3 = evidence["v3_real_weak_uplift"]
    symbolic = evidence["v4_closed_vocabulary_symbolic_control"]
    value = evidence["v4_value_ledger"]
    hybrid = evidence["v4_hybrid_incremental_value"]
    return (
        "# Boundary A: Explicit Closed-Vocabulary Policy Grammar\n\n"
        "This package mechanically separates the verified v3 DeepSeek real run "
        "from the v4 deterministic mock and symbolic/value sidecars. The mock is "
        "not real evidence.\n\n"
        f"- v3 real semantic uplift: `{v3['trajectory_qualified_semantic_uplift']}`\n"
        f"- v3 Hybrid within/cross pair success: "
        f"`{v3['hybrid_within_policy_pair_success']}/"
        f"{v3['hybrid_cross_policy_pair_success']}`\n"
        f"- v4 frozen closed-vocabulary symbolic semantic/within/cross: "
        f"`{symbolic['semantic_success']}/{symbolic['within_policy_pair_success']}/"
        f"{symbolic['cross_policy_pair_success']}`\n"
        f"- v4 value classes: `{value['value_class_counts']}`; beneficial groups: "
        f"`{value['beneficial_group_count']}`\n"
        f"- v4 Hybrid LLM calls with incremental successes per 100 calls: "
        f"`{hybrid['llm_calls']}/{hybrid['incremental_successes_per_100_calls']}`\n"
        "- Core blockers: `claim_headroom`, `beneficial_evidence_absent`\n\n"
        "## Frozen conclusion\n\n"
        f"{summary['fixed_conclusion']['statement']} This conclusion is limited to "
        "the explicit, closed vocabulary boundary and does not claim general "
        "natural-language policy solving ability.\n"
    )


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
