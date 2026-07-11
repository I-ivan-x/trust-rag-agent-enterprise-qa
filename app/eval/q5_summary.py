"""Hash-verified dual-model Q5 summary composition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.eval.q5_metrics import evaluate_q5_gates
from app.eval.q5_provenance import (
    Q5VerifiedRunManifest,
    canonical_q5_model_family,
    q5_model_deployment_fingerprint,
    q5_read_json,
    q5_sha256_file,
    validate_q5_cross_family_identities,
    verify_q5_graded_run,
)
from app.eval.q5_report import render_q5_report

Q5_DUAL_SUMMARY_FILES = frozenset(
    {
        "combined_summary.json",
        "combined_gates.json",
        "combined_report.md",
        "verified_run_ledger.json",
        "combined_manifest.json",
        "combined_hashes.json",
    }
)


class Q5DualSummaryArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output_dir: Path
    summary_path: Path
    gates_path: Path
    report_path: Path
    ledger_path: Path
    manifest_path: Path
    hashes_path: Path


def summarize_q5_model_roles(
    primary_run_dir: Path | str,
    confirmatory_run_dir: Path | str,
    output_dir: Path | str,
    *,
    primary_gold_path: Path | str,
    confirmatory_gold_path: Path | str,
) -> Q5DualSummaryArtifacts:
    """Compose primary/confirmatory runs only after full provenance verification."""

    primary = verify_q5_graded_run(primary_run_dir, primary_gold_path)
    confirmatory = verify_q5_graded_run(
        confirmatory_run_dir,
        confirmatory_gold_path,
    )
    _validate_dual_sources(primary, confirmatory)
    primary_raw = q5_read_json(primary.run_dir / "manifest.json")
    confirmatory_raw = q5_read_json(confirmatory.run_dir / "manifest.json")
    primary_graded = q5_read_json(primary.run_dir / "graded_manifest.json")
    confirmatory_graded = q5_read_json(confirmatory.run_dir / "graded_manifest.json")
    _validate_matching_experiment(
        primary_raw,
        confirmatory_raw,
        primary_graded,
        confirmatory_graded,
    )
    primary_summary = q5_read_json(primary.run_dir / "summary.json")
    confirmatory_summary = q5_read_json(confirmatory.run_dir / "summary.json")
    ledger = [_ledger_entry(primary), _ledger_entry(confirmatory)]
    combined = _combined_summary_payload(
        primary,
        confirmatory,
        primary_raw,
        primary_summary,
        confirmatory_summary,
        ledger,
    )
    gates = evaluate_q5_gates(combined)

    root = Path(output_dir)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"Q5 dual-summary directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    summary_path = root / "combined_summary.json"
    gates_path = root / "combined_gates.json"
    report_path = root / "combined_report.md"
    ledger_path = root / "verified_run_ledger.json"
    manifest_path = root / "combined_manifest.json"
    hashes_path = root / "combined_hashes.json"
    _write_json(summary_path, combined)
    _write_json(gates_path, gates)
    report_path.write_text(render_q5_report(combined, gates), encoding="utf-8")
    _write_json(ledger_path, {"schema_version": "q5-verified-ledger-v1", "runs": ledger})
    combined_manifest = _combined_manifest_payload(
        primary,
        primary_raw,
        primary_graded,
        ledger,
        gates,
    )
    _write_json(manifest_path, combined_manifest)
    hashed_paths = [summary_path, gates_path, report_path, ledger_path, manifest_path]
    _write_json(
        hashes_path,
        {
            "schema_version": "q5-dual-summary-hashes-v1",
            "artifacts": {path.name: q5_sha256_file(path) for path in hashed_paths},
        },
    )
    artifacts = Q5DualSummaryArtifacts(
        output_dir=root,
        summary_path=summary_path,
        gates_path=gates_path,
        report_path=report_path,
        ledger_path=ledger_path,
        manifest_path=manifest_path,
        hashes_path=hashes_path,
    )
    verify_q5_dual_summary(
        root,
        primary_gold_path=primary_gold_path,
        confirmatory_gold_path=confirmatory_gold_path,
    )
    return artifacts


def verify_q5_dual_summary(
    output_dir: Path | str,
    *,
    primary_gold_path: Path | str,
    confirmatory_gold_path: Path | str,
) -> dict[str, Any]:
    root = Path(output_dir)
    actual = {path.name for path in root.iterdir()}
    if actual != set(Q5_DUAL_SUMMARY_FILES):
        raise ValueError(
            "Q5 dual-summary artifact closure mismatch: "
            f"missing={sorted(Q5_DUAL_SUMMARY_FILES - actual)}, "
            f"extra={sorted(actual - Q5_DUAL_SUMMARY_FILES)}"
        )
    hashes = q5_read_json(root / "combined_hashes.json")
    expected_names = Q5_DUAL_SUMMARY_FILES - {"combined_hashes.json"}
    if not isinstance(hashes, dict) or set(hashes.get("artifacts") or {}) != set(
        expected_names
    ):
        raise ValueError("Q5 dual-summary hash inventory mismatch")
    for filename, expected in hashes["artifacts"].items():
        if q5_sha256_file(root / filename) != expected:
            raise ValueError(f"Q5 dual-summary hash mismatch: {filename}")
    summary = q5_read_json(root / "combined_summary.json")
    gates = q5_read_json(root / "combined_gates.json")
    ledger_payload = q5_read_json(root / "verified_run_ledger.json")
    manifest = q5_read_json(root / "combined_manifest.json")
    ledger = ledger_payload.get("runs") if isinstance(ledger_payload, dict) else None
    if not isinstance(ledger, list) or len(ledger) != 2:
        raise ValueError("Q5 dual-summary ledger must contain exactly two runs")
    if summary.get("run_metadata", {}).get("verified_run_ledger") != ledger:
        raise ValueError("Q5 dual-summary ledger provenance mismatch")
    if manifest.get("source_runs") != ledger:
        raise ValueError("Q5 dual-summary manifest provenance mismatch")
    verified_sources = [
        verify_q5_graded_run(ledger[0]["run_dir"], primary_gold_path),
        verify_q5_graded_run(ledger[1]["run_dir"], confirmatory_gold_path),
    ]
    if [_ledger_entry(source) for source in verified_sources] != ledger:
        raise ValueError("Q5 dual-summary source run hashes changed")
    primary, confirmatory = verified_sources
    _validate_dual_sources(primary, confirmatory)
    primary_raw = q5_read_json(primary.run_dir / "manifest.json")
    confirmatory_raw = q5_read_json(confirmatory.run_dir / "manifest.json")
    primary_graded = q5_read_json(primary.run_dir / "graded_manifest.json")
    confirmatory_graded = q5_read_json(confirmatory.run_dir / "graded_manifest.json")
    _validate_matching_experiment(
        primary_raw,
        confirmatory_raw,
        primary_graded,
        confirmatory_graded,
    )
    primary_summary = q5_read_json(primary.run_dir / "summary.json")
    confirmatory_summary = q5_read_json(confirmatory.run_dir / "summary.json")
    expected_summary = _combined_summary_payload(
        primary,
        confirmatory,
        primary_raw,
        primary_summary,
        confirmatory_summary,
        ledger,
    )
    if summary != expected_summary:
        raise ValueError("Q5 dual-summary metrics/model-role provenance mismatch")
    if gates != evaluate_q5_gates(summary):
        raise ValueError("Q5 dual-summary gates are not reproducible")
    if manifest != _combined_manifest_payload(
        primary,
        primary_raw,
        primary_graded,
        ledger,
        gates,
    ):
        raise ValueError("Q5 dual-summary manifest source provenance mismatch")
    if (root / "combined_report.md").read_text(
        encoding="utf-8"
    ) != render_q5_report(summary, gates):
        raise ValueError("Q5 dual-summary report is not reproducible")
    return {"summary": summary, "gates": gates, "ledger": ledger}


def _combined_summary_payload(
    primary: Q5VerifiedRunManifest,
    confirmatory: Q5VerifiedRunManifest,
    primary_raw: dict[str, Any],
    primary_summary: dict[str, Any],
    confirmatory_summary: dict[str, Any],
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    if primary_summary.get("analytic_controls") != confirmatory_summary.get(
        "analytic_controls"
    ):
        raise ValueError("Q5 dual-model analytic controls do not match")
    mode = primary.mode if primary.mode == confirmatory.mode else "mixed"
    return {
        "schema_version": "q5-dual-model-summary-v1",
        "metric_type": "q5_outcome",
        "run_id": f"{primary.run_id}+{confirmatory.run_id}",
        "k": primary_summary["k"],
        "seed": primary_summary["seed"],
        "bootstrap_resamples": primary_summary["bootstrap_resamples"],
        "by_system": primary_summary["by_system"],
        "comparisons": primary_summary["comparisons"],
        "analytic_controls": primary_summary["analytic_controls"],
        "run_metadata": {
            "mode": mode,
            "mock_used": primary.mock_used or confirmatory.mock_used,
            "real_run": primary.real_run and confirmatory.real_run,
            "dataset_partition": primary_raw["dataset_partition"],
            "model_role": "dual",
            "verified_run_ledger": ledger,
        },
        "by_model_role": {
            "primary": primary_summary["by_model_role"]["primary"],
            "confirmatory": confirmatory_summary["by_model_role"]["confirmatory"],
        },
    }


def _combined_manifest_payload(
    primary: Q5VerifiedRunManifest,
    primary_raw: dict[str, Any],
    primary_graded: dict[str, Any],
    ledger: list[dict[str, Any]],
    gates: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "q5-dual-summary-manifest-v1",
        "source_runs": ledger,
        "shared_provenance": {
            "git_commit_sha": primary.git_commit_sha,
            "prompt_sha256": primary.prompt_sha256,
            "dataset_hashes": primary_raw["dataset_hashes"],
            "gold_sha256": primary_graded["dataset_hashes"]["gold"],
            "systems": primary_raw["systems"],
            "seed": primary_raw["seed"],
            "k": primary_raw["k"],
            "bootstrap": primary_raw["bootstrap"],
        },
        "headline_eligible": gates["q5_headline_eligible"],
    }


def _validate_dual_sources(
    primary: Q5VerifiedRunManifest,
    confirmatory: Q5VerifiedRunManifest,
) -> None:
    if primary.model_role != "primary":
        raise ValueError("Q5 primary source run does not have primary model role")
    if confirmatory.model_role != "confirmatory":
        raise ValueError(
            "Q5 confirmatory source run does not have confirmatory model role"
        )
    if primary.run_id == confirmatory.run_id:
        raise ValueError("Q5 dual-model source run_ids must be distinct")
    if primary.git_commit_sha != confirmatory.git_commit_sha:
        raise ValueError("Q5 dual-model source commits do not match")
    if primary.prompt_sha256 != confirmatory.prompt_sha256:
        raise ValueError("Q5 dual-model prompt hashes do not match")
    validate_q5_cross_family_identities(
        primary.model_identities,
        confirmatory.model_identities,
    )


def _validate_matching_experiment(
    primary_raw: dict[str, Any],
    confirmatory_raw: dict[str, Any],
    primary_graded: dict[str, Any],
    confirmatory_graded: dict[str, Any],
) -> None:
    for field in (
        "systems",
        "seed",
        "k",
        "bootstrap",
        "dataset_partition",
        "case_ids",
        "trial_key_sha256",
        "dataset_hashes",
        "prompt",
    ):
        if primary_raw.get(field) != confirmatory_raw.get(field):
            raise ValueError(f"Q5 dual-model experiment provenance mismatch: {field}")
    if primary_graded.get("dataset_hashes", {}).get("gold") != (
        confirmatory_graded.get("dataset_hashes", {}).get("gold")
    ):
        raise ValueError("Q5 dual-model gold hash provenance mismatch")


def _ledger_entry(source: Q5VerifiedRunManifest) -> dict[str, Any]:
    return {
        "verified": True,
        "run_id": source.run_id,
        "run_dir": source.run_dir.as_posix(),
        "model_role": source.model_role,
        "raw_manifest_sha256": source.raw_manifest_sha256,
        "graded_manifest_sha256": source.graded_manifest_sha256,
        "summary_sha256": source.summary_sha256,
        "gates_sha256": source.gates_sha256,
        "gold_sha256": source.gold_sha256,
        "model_identities": [
            identity.model_dump(mode="json") for identity in source.model_identities
        ],
        "canonical_model_families": sorted(
            {
                canonical_q5_model_family(identity)
                for identity in source.model_identities
            }
        ),
        "model_deployments": sorted(
            [
                list(q5_model_deployment_fingerprint(identity))
                for identity in source.model_identities
            ]
        ),
        "provider_model_pairs": source.provider_model_pairs,
        "git_commit_sha": source.git_commit_sha,
        "prompt_sha256": source.prompt_sha256,
        "mode": source.mode,
        "mock_used": source.mock_used,
        "real_run": source.real_run,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
