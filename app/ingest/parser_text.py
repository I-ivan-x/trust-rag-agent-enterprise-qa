from pathlib import Path

from app.core.ids import normalize_slug
from app.ingest.metadata_extractor import build_document_metadata, extract_front_matter
from app.schemas.document import ParsedDocument, ParsedSection, RawDocument


def parse_text_document(raw_doc: RawDocument) -> ParsedDocument:
    front_matter, body = extract_front_matter(raw_doc.content)
    title = (
        front_matter.get("title")
        or _first_non_empty_line(body)
        or Path(raw_doc.source_path).stem
    )
    metadata = build_document_metadata({**front_matter, "title": title}, raw_doc.source_path)
    lines = body.splitlines()
    line_end = max(len(lines), 1)
    text = body.strip()
    section = ParsedSection(
        section_id=f"{metadata.doc_id}::sec-{normalize_slug(title)}-0001",
        title=title,
        heading_level=1,
        section_path=[title],
        text=text,
        line_start=1,
        line_end=line_end,
        children=[],
    )
    return ParsedDocument(metadata=metadata, sections=[section] if text else [], raw_text=body)


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None
