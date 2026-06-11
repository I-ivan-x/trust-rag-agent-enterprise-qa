from __future__ import annotations

import json
from pathlib import Path

from scripts.ingest_corpus import run_ingest


def test_public_corpus_ingest_applies_overlay_to_documents_and_chunks(tmp_path: Path) -> None:
    corpus = tmp_path / "public_corpus"
    output = tmp_path / "generated" / "public"
    _write_doc(corpus / "active" / "intro.md", "Intro")
    _write_doc(corpus / "security" / "keys.md", "Keys")
    overlay_path = corpus / "overlay" / "metadata_overlay.yaml"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.write_text(
        """seed: 42
defaults:
  status: active
  access_level: internal
  allowed_roles: [employee, engineer]
rules:
  - match: "security/**"
    access_level: restricted
    allowed_roles: [security_admin]
documents: []
""",
        encoding="utf-8",
    )

    summary = run_ingest(
        input_dir=corpus,
        output_dir=output,
        eval_path=None,
        review_path=None,
        overlay_path=overlay_path,
    )
    documents = _read_jsonl(output / "documents.jsonl")
    chunks = _read_jsonl(output / "chunks.jsonl")
    key_chunks = [chunk for chunk in chunks if chunk["doc_id"] == "doc-keys"]

    assert summary["overlay_applied"] is True
    assert summary["parsed_documents"] == 2
    assert documents
    assert chunks
    assert key_chunks
    assert key_chunks[0]["access_level"] == "restricted"
    assert key_chunks[0]["allowed_roles"] == ["security_admin"]
    assert key_chunks[0]["metadata_origin"] == "overlay"


def _write_doc(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
doc_id: doc-{title.lower()}
title: {title}
doc_type: public_doc
status: active
version: "1.0"
access_level: internal
allowed_roles: [employee, engineer]
language: en
source_path: {path.as_posix()}
corpus_source: public_external
source_origin: public_repo
source_license_note: Public documentation fixture for ingest tests.
metadata_origin: native
source_url: https://example.com/{title.lower()}
---

# {title}

## Overview

Public body text for {title}.
""",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
