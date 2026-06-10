from pydantic import BaseModel, Field, field_validator

from app.core.enums import (
    AccessLevel,
    CorpusSource,
    DocumentStatus,
    MetadataOrigin,
    SourceOrigin,
)


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    chunk_index: int = Field(ge=0)
    text: str
    section_path: list[str] = Field(default_factory=list)
    heading_level: int | None = Field(default=None, ge=1)
    token_count: int = Field(default=0, ge=0)
    char_count: int = Field(default=0, ge=0)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    parent_section_id: str | None = None
    status: DocumentStatus = DocumentStatus.active
    version: str
    allowed_roles: list[str] = Field(default_factory=lambda: ["employee"])
    access_level: AccessLevel = AccessLevel.internal
    tags: list[str] = Field(default_factory=list)

    corpus_source: CorpusSource = CorpusSource.synthetic_fixture
    source_origin: SourceOrigin = SourceOrigin.generated
    source_license_note: str | None = None
    hard_negative_group_id: str | None = None
    metadata_origin: MetadataOrigin = MetadataOrigin.native
    conflict_group_id: str | None = None
    is_authoritative: bool = False

    @field_validator("chunk_id", "doc_id", "text")
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


class ChunkConfig(BaseModel):
    chunk_max_tokens: int = Field(default=500, gt=0)
    chunk_overlap_tokens: int = Field(default=80, ge=0)

