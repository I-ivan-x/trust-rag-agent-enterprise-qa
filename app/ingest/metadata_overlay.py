from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

from app.core.enums import MetadataOrigin
from app.schemas.document import ParsedDocument

DEFAULT_PUBLIC_OVERLAY_PATH = Path("data/public_corpus/overlay/metadata_overlay.yaml")


class OverlayRule(BaseModel):
    match: str
    values: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect_values(cls, obj: Any) -> Any:
        if isinstance(obj, dict) and "match" in obj:
            values = {key: value for key, value in obj.items() if key != "match"}
            return {"match": obj["match"], "values": values}
        return obj


class OverlayDocumentOverride(BaseModel):
    path: str
    values: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect_values(cls, obj: Any) -> Any:
        if isinstance(obj, dict) and "path" in obj:
            values = {key: value for key, value in obj.items() if key != "path"}
            return {"path": obj["path"], "values": values}
        return obj


class MetadataOverlay(BaseModel):
    seed: int = 42
    defaults: dict[str, Any] = Field(default_factory=dict)
    rules: list[OverlayRule] = Field(default_factory=list)
    documents: list[OverlayDocumentOverride] = Field(default_factory=list)


class OverlayStats(BaseModel):
    overlay_applied: bool
    document_count: int
    overlay_modified_count: int
    restricted_or_confidential_count: int
    deprecated_count: int
    restricted_or_confidential_ratio: float
    deprecated_ratio: float


def load_metadata_overlay(path: Path | None) -> MetadataOverlay | None:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Metadata overlay not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Metadata overlay YAML must be a mapping")
    return MetadataOverlay.model_validate(data)


def apply_metadata_overlay(
    parsed_documents: list[ParsedDocument],
    overlay: MetadataOverlay | None,
    corpus_root: Path | None = None,
) -> OverlayStats:
    if overlay is None:
        return _stats(parsed_documents, overlay_applied=False)

    document_overrides = {
        _normalize_path(document.path): document.values for document in overlay.documents
    }
    for parsed_doc in parsed_documents:
        relative_path = _document_relative_path(parsed_doc, corpus_root)
        updates: dict[str, Any] = {}
        updates.update(overlay.defaults)
        for rule in overlay.rules:
            if fnmatch.fnmatch(relative_path, _normalize_path(rule.match)):
                updates.update(rule.values)
        updates.update(document_overrides.get(relative_path, {}))
        _apply_updates(parsed_doc, updates)

    return _stats(parsed_documents, overlay_applied=True)


def overlay_stats(parsed_documents: list[ParsedDocument]) -> OverlayStats:
    return _stats(parsed_documents, overlay_applied=False)


def _apply_updates(parsed_doc: ParsedDocument, updates: dict[str, Any]) -> None:
    if not updates:
        return
    current = parsed_doc.metadata
    payload = current.model_dump(mode="json")
    changed = False
    for key, value in updates.items():
        if key not in payload:
            continue
        if payload[key] != value:
            payload[key] = value
            changed = True
    if changed:
        payload["metadata_origin"] = MetadataOrigin.overlay.value
        parsed_doc.metadata = current.__class__.model_validate(payload)


def _stats(parsed_documents: list[ParsedDocument], overlay_applied: bool) -> OverlayStats:
    total = len(parsed_documents)
    modified = sum(
        1 for doc in parsed_documents if doc.metadata.metadata_origin == MetadataOrigin.overlay
    )
    restricted = sum(
        1
        for doc in parsed_documents
        if doc.metadata.access_level.value in {"restricted", "confidential"}
    )
    deprecated = sum(1 for doc in parsed_documents if doc.metadata.status.value == "deprecated")
    return OverlayStats(
        overlay_applied=overlay_applied,
        document_count=total,
        overlay_modified_count=modified,
        restricted_or_confidential_count=restricted,
        deprecated_count=deprecated,
        restricted_or_confidential_ratio=restricted / total if total else 0.0,
        deprecated_ratio=deprecated / total if total else 0.0,
    )


def _document_relative_path(parsed_doc: ParsedDocument, corpus_root: Path | None) -> str:
    source_path = _normalize_path(parsed_doc.metadata.source_path)
    if corpus_root is not None:
        root = _normalize_path(corpus_root)
        if source_path.startswith(f"{root}/"):
            return source_path[len(root) + 1 :]
        resolved_root = _normalize_path(corpus_root.resolve())
        resolved_source = _normalize_path(Path(source_path).resolve())
        if resolved_source.startswith(f"{resolved_root}/"):
            return resolved_source[len(resolved_root) + 1 :]
    return source_path


def _normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/").strip("/")
