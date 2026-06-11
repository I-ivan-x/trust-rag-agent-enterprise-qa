from pydantic import BaseModel, Field

from app.core.enums import CitationSupportType, CitationVerificationStatus


class CitationLocator(BaseModel):
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    source_path: str


class Citation(BaseModel):
    citation_id: str
    doc_id: str
    chunk_id: str
    title: str
    section_path: list[str] = Field(default_factory=list)
    locator: CitationLocator
    support_type: CitationSupportType = CitationSupportType.direct
    verification_status: CitationVerificationStatus = CitationVerificationStatus.unchecked


class VerificationResult(BaseModel):
    status: CitationVerificationStatus = CitationVerificationStatus.not_checked
    invalid_citations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    supported_claim_ids: list[str] = Field(default_factory=list)
    unsupported_claim_ids: list[str] = Field(default_factory=list)
