from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.enums import (
    AccessLevel,
    CorpusSource,
    DocumentStatus,
    DocumentType,
    MetadataOrigin,
    SourceOrigin,
)


class DocumentMetadata(BaseModel):
    doc_id: str
    title: str
    doc_type: DocumentType
    status: DocumentStatus
    version: str
    created_at: date | None = None
    updated_at: date | None = None
    effective_date: date | None = None
    owner_team: str | None = None
    department: str | None = None
    access_level: AccessLevel = AccessLevel.internal
    allowed_roles: list[str] = Field(default_factory=lambda: ["employee"])
    tags: list[str] = Field(default_factory=list)
    language: str = "en"
    source_path: str
    supersedes_doc_id: str | None = None
    superseded_by: str | None = None
    conflict_group_id: str | None = None
    is_authoritative: bool = False

    corpus_source: CorpusSource = CorpusSource.synthetic_fixture
    source_origin: SourceOrigin = SourceOrigin.generated
    source_license_note: str | None = None
    source_url: str | None = None
    hard_negative_group_id: str | None = None
    metadata_origin: MetadataOrigin = MetadataOrigin.native

    @field_validator("doc_id", "title")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("allowed_roles")
    @classmethod
    def _roles_must_not_be_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("allowed_roles must not be empty")
        return value


class RawDocument(BaseModel):
    source_path: str
    content: str
    encoding: str = "utf-8"
    metadata_hint: dict[str, Any] = Field(default_factory=dict)


class ParsedSection(BaseModel):
    section_id: str
    title: str
    heading_level: int = Field(ge=1)
    section_path: list[str] = Field(default_factory=list)
    text: str
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    children: list[ParsedSection] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    metadata: DocumentMetadata
    sections: list[ParsedSection] = Field(default_factory=list)
    raw_text: str
