import pytest
from pydantic import ValidationError

from app.core.enums import CorpusSource, MetadataOrigin, SourceOrigin
from app.ingest.metadata_extractor import build_document_metadata, extract_front_matter
from app.schemas.document import DocumentMetadata


def test_complete_front_matter_builds_document_metadata() -> None:
    raw_text = """---
doc_id: doc-example
title: Example Doc
doc_type: api_spec
status: active
version: v2
access_level: confidential
allowed_roles:
  - engineer
tags:
  - api
language: en
source_path: stale/path.md
corpus_source: synthetic_fixture
source_origin: generated
metadata_origin: native
---

# Example
"""
    front_matter, body = extract_front_matter(raw_text)
    metadata = build_document_metadata(front_matter, "actual/path.md")

    assert body.lstrip().startswith("# Example")
    assert metadata.doc_id == "doc-example"
    assert metadata.source_path == "actual/path.md"
    assert metadata.allowed_roles == ["engineer"]


def test_missing_optional_fields_get_defaults() -> None:
    metadata = build_document_metadata({"title": "Fallback Metadata"}, "docs/fallback.md")

    assert metadata.language == "en"
    assert metadata.allowed_roles == ["employee"]
    assert metadata.tags == []
    assert metadata.corpus_source == CorpusSource.synthetic_fixture
    assert metadata.source_origin == SourceOrigin.generated
    assert metadata.metadata_origin == MetadataOrigin.native


def test_empty_allowed_roles_are_corrected_to_default() -> None:
    metadata = build_document_metadata(
        {"title": "Roles", "allowed_roles": [], "doc_type": "handbook"},
        "docs/roles.md",
    )

    assert metadata.allowed_roles == ["employee"]


def test_schema_still_rejects_empty_allowed_roles_directly() -> None:
    with pytest.raises(ValidationError):
        DocumentMetadata(
            doc_id="doc-invalid",
            title="Invalid",
            doc_type="handbook",
            status="active",
            version="v1",
            source_path="docs/invalid.md",
            allowed_roles=[],
        )


def test_source_path_uses_actual_file_path() -> None:
    metadata = build_document_metadata(
        {
            "doc_id": "doc-source",
            "title": "Source",
            "source_path": "frontmatter/path.md",
        },
        "real/path.md",
    )

    assert metadata.source_path == "real/path.md"
