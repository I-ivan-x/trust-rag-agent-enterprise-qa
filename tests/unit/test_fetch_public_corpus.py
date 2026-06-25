from __future__ import annotations

from pathlib import Path

import yaml

from scripts import run_q3_governance_ablation as q3_ablation
from scripts.fetch_public_corpus import (
    _default_output_dir,
    write_combined_metadata_overlay,
)


def test_k8s_default_output_uses_ops_namespace() -> None:
    assert _default_output_dir("k8s") == Path("data/ops_runbook_corpus")


def test_q3_ablation_uses_isolated_ops_generated_dir() -> None:
    assert q3_ablation.OPS_CORPUS_DIR == Path("data/ops_runbook_corpus")
    assert q3_ablation.OPS_GENERATED_DIR == Path("data/generated/ops_runbook")
    assert q3_ablation.OPS_CHUNKS_PATH != Path("data/generated/public/chunks.jsonl")


def test_combined_overlay_prefixes_namespaced_ops_once(tmp_path: Path) -> None:
    corpus = tmp_path / "public_corpus"
    _write_overlay(
        corpus / "overlay" / "metadata_overlay.yaml",
        rules=[{"match": "security/**", "access_level": "restricted"}],
        documents=[{"path": "deprecated/old.md", "status": "deprecated"}],
    )
    _write_overlay(
        corpus / "ops" / "overlay" / "metadata_overlay.yaml",
        rules=[{"match": "security/**", "access_level": "restricted"}],
        documents=[{"path": "active/k8s.md", "overlay_relation_note": {"type": "anchor"}}],
    )

    write_combined_metadata_overlay(corpus)
    write_combined_metadata_overlay(corpus)

    combined = yaml.safe_load(
        (corpus / "overlay" / "metadata_overlay.yaml").read_text(encoding="utf-8")
    )
    assert [rule["match"] for rule in combined["rules"]] == [
        "security/**",
        "ops/**",
        "ops/security/**",
    ]
    assert [document["path"] for document in combined["documents"]] == [
        "deprecated/old.md",
        "ops/active/k8s.md",
    ]


def _write_overlay(
    path: Path,
    *,
    rules: list[dict],
    documents: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "seed": 42,
                "defaults": {"status": "active"},
                "rules": rules,
                "documents": documents,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
