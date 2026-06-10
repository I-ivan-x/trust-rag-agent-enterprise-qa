from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.enums import (
    AccessLevel,
    CorpusSource,
    DocumentStatus,
    DocumentType,
    MetadataOrigin,
    SourceOrigin,
)
from app.core.ids import make_doc_id
from app.schemas.document import DocumentMetadata


def extract_front_matter(raw_text: str) -> tuple[dict[str, Any], str]:
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw_text

    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break

    if closing_index is None:
        return {}, raw_text

    front_matter_text = "\n".join(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1 :])
    if raw_text.endswith("\n") and body:
        body += "\n"

    parsed = yaml.safe_load(front_matter_text) or {}
    if not isinstance(parsed, dict):
        raise ValueError("YAML front matter must parse to a mapping")
    return parsed, body


def build_document_metadata(front_matter: dict[str, Any], source_path: str) -> DocumentMetadata:
    data = dict(front_matter)
    title = _clean_string(data.get("title")) or _title_from_source_path(source_path)
    doc_type = data.get("doc_type") or DocumentType.public_doc
    version = _clean_string(data.get("version")) or "v1"
    doc_id = _clean_string(data.get("doc_id")) or make_doc_id(str(doc_type), title, version)

    allowed_roles = _normalize_list(data.get("allowed_roles")) or ["employee"]
    tags = _normalize_list(data.get("tags"))

    payload = {
        **data,
        "doc_id": doc_id,
        "title": title,
        "doc_type": doc_type,
        "status": data.get("status") or DocumentStatus.active,
        "version": version,
        "access_level": data.get("access_level") or AccessLevel.internal,
        "allowed_roles": allowed_roles,
        "tags": tags,
        "language": _clean_string(data.get("language")) or "en",
        "source_path": source_path,
        "corpus_source": data.get("corpus_source") or CorpusSource.synthetic_fixture,
        "source_origin": data.get("source_origin") or SourceOrigin.generated,
        "metadata_origin": data.get("metadata_origin") or MetadataOrigin.native,
        "is_authoritative": bool(data.get("is_authoritative", False)),
    }
    return DocumentMetadata.model_validate(payload)


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _title_from_source_path(source_path: str) -> str:
    stem = Path(source_path).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(word.capitalize() for word in stem.split()) or "Untitled Document"

