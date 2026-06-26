"""Q4-P7: run manifest -- the reproducibility root for an eval run (SPEC_Q4_P6_P7 §2).

``build_run_manifest`` returns a JSON-serialisable dict capturing everything needed to
reproduce a governance run: models, prompt version, retriever index fingerprint, corpus
namespace, seed, k, mock/real mode, cost, latency, git commit SHA, and a read-only
snapshot of the anti-gaming thresholds (recorded for provenance, never used in scoring).

This module only records provenance; it does not change any metric computation or run
behaviour.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.eval.govern_metrics import AUTH_PRECISION_FLOOR, OVER_ESCALATION_CEIL

GOVERNANCE_PROMPT_VERSION = "govern-controller-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def git_commit_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except Exception:  # pragma: no cover - git always present in this repo
        return None


def _index_fingerprint(index_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not index_summary:
        return {"chunks_loaded": None, "chunks_path": None, "chunks_sha256": None}
    chunks_path = index_summary.get("chunks_path")
    sha = None
    if chunks_path:
        path = Path(chunks_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if path.is_file():
            sha = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        else:
            sha = hashlib.sha256(str(chunks_path).encode("utf-8")).hexdigest()[:16]
    return {
        "chunks_loaded": index_summary.get("chunks_loaded"),
        "chunks_path": chunks_path,
        "chunks_sha256": sha,
        "vector_count": index_summary.get("vector_count"),
        "keyword_count": index_summary.get("keyword_count"),
        "qdrant_collection": index_summary.get("qdrant_collection"),
    }


def _corpus_namespace(index_summary: dict[str, Any] | None) -> str | None:
    if not index_summary:
        return None
    chunks_path = index_summary.get("chunks_path")
    if not chunks_path:
        return None
    # e.g. data/generated/ops_runbook/chunks.jsonl -> ops_runbook
    parent = Path(chunks_path).parent.name
    return parent or None


def build_run_manifest(
    *,
    run_id: str,
    systems: list[str],
    split: str | None,
    k: int,
    mode: str,
    settings: Any = None,
    summary: dict[str, Any] | None = None,
    index_summary: dict[str, Any] | None = None,
    commit_sha: str | None = None,
    seed: int | None = None,
    prompt_version: str = GOVERNANCE_PROMPT_VERSION,
    latency_seconds: float | None = None,
    cost: dict[str, Any] | None = None,
    preregister_ref: str | None = None,
) -> dict[str, Any]:
    summary = summary or {}
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    mock_used = bool(summary.get("mock_used", mode == "mock"))
    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit_sha": commit_sha or git_commit_sha(),
        "split": split,
        "systems": list(systems),
        "k": k,
        "mode": mode,
        "mock_used": mock_used,
        "vector_unavailable": bool(summary.get("vector_unavailable", False)),
        "reranker_unavailable": bool(summary.get("reranker_unavailable", False)),
        "model": {
            "answer": {
                "provider": getattr(settings, "llm_provider", None),
                "name": getattr(settings, "llm_model_name", None),
            },
            "controller": {
                "provider": getattr(settings, "llm_provider", None),
                "name": getattr(settings, "llm_model_name", None),
            },
            "embedding": {
                "provider": getattr(settings, "embedding_provider", None),
                "name": getattr(settings, "embedding_model_name", None),
            },
            "reranker": {
                "provider": getattr(settings, "reranker_provider", None),
                "name": getattr(settings, "reranker_model_name", None),
            },
        },
        "prompt_version": prompt_version,
        "controller_type": ",".join(systems),
        "retriever_index_fingerprint": _index_fingerprint(index_summary),
        "corpus_namespace": _corpus_namespace(index_summary),
        "seed": seed,
        "cost": cost or {"llm_calls": None, "total_tokens": None},
        "latency_seconds": latency_seconds,
        "preregister_ref": preregister_ref,
        "thresholds_snapshot": {
            "AUTH_PRECISION_FLOOR": AUTH_PRECISION_FLOOR,
            "OVER_ESCALATION_CEIL": OVER_ESCALATION_CEIL,
            "note": "Recorded for provenance only; not used in scoring (thresholds are frozen).",
        },
    }


def write_run_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    import json

    path = Path(run_dir) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
