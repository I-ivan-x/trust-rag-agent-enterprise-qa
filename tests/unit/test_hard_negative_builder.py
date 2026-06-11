from __future__ import annotations

import json
from pathlib import Path

from app.corpus.hard_negative_builder import build_hard_negative_corpus


def test_hard_negative_manifest_can_be_generated(tmp_path: Path) -> None:
    public = tmp_path / "public_corpus"
    output = tmp_path / "hard_negative_corpus"
    for index in range(4):
        _write_public_doc(public / "active" / f"doc-{index}.md", index)

    summary = build_hard_negative_corpus(public, output, pair_count=3)
    manifest_path = output / "hard_negative_manifest.jsonl"
    records = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]

    assert summary["pair_count"] == 3
    assert manifest_path.exists()
    assert len(records) == 3
    assert all(record["hard_negative_group_id"] for record in records)
    assert all(record["source_path_a"] for record in records)
    assert {record["pair_type"] for record in records} <= {
        "adjacent_topic",
        "similar_title",
    }
    assert not any(
        record["pair_type"]
        in {
            "adjacent_version",
            "same_term_different_limit",
            "deprecated_vs_active",
            "official_doc_vs_meeting_note",
        }
        for record in records
    )
    assert all("Public Doc" in record["why_hard"] for record in records)
    assert all("Public Doc" in record["expected_confusion"] for record in records)
    assert (output / "hn-fastapi-0001").exists()


def _write_public_doc(path: Path, index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
doc_id: doc-public-{index}
title: Public Doc {index}
doc_type: public_doc
status: active
version: "1.0"
access_level: internal
allowed_roles: [employee, engineer]
language: en
source_path: {path.as_posix()}
corpus_source: public_external
source_origin: public_repo
source_license_note: Public documentation fixture for hard negative tests.
metadata_origin: native
source_url: https://example.com/public-{index}
---

# Public Doc {index}

This public document contains similar technical terminology for retrieval tests.
""",
        encoding="utf-8",
    )
