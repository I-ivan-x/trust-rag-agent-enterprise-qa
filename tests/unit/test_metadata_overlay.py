from __future__ import annotations

from pathlib import Path

from app.core.enums import AccessLevel, DocumentStatus, MetadataOrigin
from app.ingest.loader import load_corpus
from app.ingest.metadata_overlay import apply_metadata_overlay, load_metadata_overlay
from app.ingest.parser_markdown import parse_markdown_document


def test_overlay_defaults_glob_and_exact_override(tmp_path: Path) -> None:
    corpus = tmp_path / "public"
    _write_doc(corpus / "active" / "intro.md", "Intro")
    _write_doc(corpus / "security" / "keys.md", "Keys")
    _write_doc(corpus / "deprecated" / "old.md", "Old")
    overlay_path = _write_overlay(corpus)

    docs = [parse_markdown_document(raw) for raw in load_corpus(corpus)]
    overlay = load_metadata_overlay(overlay_path)
    stats = apply_metadata_overlay(docs, overlay, corpus_root=corpus)
    by_title = {doc.metadata.title: doc.metadata for doc in docs}

    assert by_title["Intro"].access_level == AccessLevel.internal
    assert by_title["Intro"].metadata_origin == MetadataOrigin.native
    assert by_title["Keys"].access_level == AccessLevel.restricted
    assert by_title["Keys"].allowed_roles == ["security_admin"]
    assert by_title["Keys"].metadata_origin == MetadataOrigin.overlay
    assert by_title["Old"].status == DocumentStatus.deprecated
    assert by_title["Old"].version == "0.9"
    assert by_title["Old"].metadata_origin == MetadataOrigin.overlay
    assert stats.restricted_or_confidential_count == 1
    assert stats.deprecated_count == 1


def test_overlay_seed_is_reproducible(tmp_path: Path) -> None:
    corpus = tmp_path / "public"
    _write_doc(corpus / "security" / "keys.md", "Keys")
    overlay_path = _write_overlay(corpus)

    first = [parse_markdown_document(raw) for raw in load_corpus(corpus)]
    second = [parse_markdown_document(raw) for raw in load_corpus(corpus)]
    overlay = load_metadata_overlay(overlay_path)

    first_stats = apply_metadata_overlay(first, overlay, corpus_root=corpus)
    second_stats = apply_metadata_overlay(second, overlay, corpus_root=corpus)

    assert overlay.seed == 42
    assert first[0].metadata == second[0].metadata
    assert first_stats == second_stats


def test_overlay_does_not_rewrite_source_body(tmp_path: Path) -> None:
    corpus = tmp_path / "public"
    source_path = corpus / "security" / "keys.md"
    _write_doc(source_path, "Keys", body="Original public body text.")
    overlay_path = _write_overlay(corpus)
    raw_before = source_path.read_text(encoding="utf-8")

    docs = [parse_markdown_document(raw) for raw in load_corpus(corpus)]
    apply_metadata_overlay(docs, load_metadata_overlay(overlay_path), corpus_root=corpus)

    assert source_path.read_text(encoding="utf-8") == raw_before
    assert "Original public body text." in docs[0].raw_text


def _write_doc(path: Path, title: str, body: str | None = None) -> None:
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
source_license_note: Public documentation fixture for overlay tests.
metadata_origin: native
source_url: https://example.com/{title.lower()}
---

# {title}

{body or "Original public body text."}
""",
        encoding="utf-8",
    )


def _write_overlay(corpus: Path) -> Path:
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
  - match: "deprecated/**"
    status: deprecated
documents:
  - path: "deprecated/old.md"
    version: "0.9"
    superseded_by: "active/intro.md"
""",
        encoding="utf-8",
    )
    return overlay_path
