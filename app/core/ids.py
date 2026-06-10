from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

_SLUG_PATTERN = re.compile(r"[^a-z0-9_-]+")
_SEPARATOR_PATTERN = re.compile(r"[-_]{2,}")


def normalize_slug(text: str) -> str:
    lowered = text.strip().lower().replace(" ", "-")
    ascii_text = lowered.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_PATTERN.sub("-", ascii_text)
    slug = _SEPARATOR_PATTERN.sub("-", slug).strip("-_")
    if slug:
        return slug
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"item-{digest}"


def make_doc_id(doc_type: str, title: str, version: str | None = None) -> str:
    parts = [normalize_slug(doc_type), normalize_slug(title)]
    if version:
        parts.append(normalize_slug(version))
    return "doc-" + "-".join(parts)


def make_chunk_id(doc_id: str, chunk_index: int) -> str:
    if chunk_index < 0:
        raise ValueError("chunk_index must be non-negative")
    return f"{doc_id}::chunk-{chunk_index:04d}"


def make_trace_id(now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    suffix = hashlib.sha1(current.isoformat().encode("utf-8")).hexdigest()[:8]
    return f"trace-{current:%Y%m%d}-{suffix}"


def make_eval_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    suffix = hashlib.sha1(current.isoformat().encode("utf-8")).hexdigest()[:8]
    return f"eval-{current:%Y%m%d}-{suffix}"


def make_citation_id(index: int) -> str:
    if index < 1:
        raise ValueError("citation index starts at 1")
    return f"CIT-{index:04d}"

