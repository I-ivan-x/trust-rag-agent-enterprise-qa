from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.ids import normalize_slug
from app.ingest.metadata_extractor import build_document_metadata, extract_front_matter
from app.schemas.document import ParsedDocument, ParsedSection, RawDocument

_HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+?)\s*$")


@dataclass
class _SectionDraft:
    title: str
    heading_level: int
    section_path: list[str]
    parent_index: int | None
    lines: list[tuple[int, str]] = field(default_factory=list)


def parse_markdown_document(raw_doc: RawDocument) -> ParsedDocument:
    front_matter, body = extract_front_matter(raw_doc.content)
    body_start_line = _body_start_line(raw_doc.content)
    if not front_matter.get("title"):
        inferred_title = _first_heading_title(body)
        if inferred_title:
            front_matter = {**front_matter, "title": inferred_title}

    metadata = build_document_metadata(front_matter, raw_doc.source_path)
    drafts = _parse_section_drafts(body, body_start_line)
    sections = _finalize_sections(drafts, metadata.doc_id)
    return ParsedDocument(metadata=metadata, sections=sections, raw_text=body)


def _parse_section_drafts(body: str, body_start_line: int) -> list[_SectionDraft]:
    drafts: list[_SectionDraft] = []
    stack: list[int] = []
    current_index: int | None = None
    in_code_block = False

    for offset, line in enumerate(body.splitlines(), start=0):
        line_number = body_start_line + offset
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block

        heading_match = None if in_code_block else _HEADING_PATTERN.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            while stack and drafts[stack[-1]].heading_level >= level:
                stack.pop()
            parent_index = stack[-1] if stack else None
            parent_path = drafts[parent_index].section_path if parent_index is not None else []
            drafts.append(
                _SectionDraft(
                    title=title,
                    heading_level=level,
                    section_path=[*parent_path, title],
                    parent_index=parent_index,
                )
            )
            current_index = len(drafts) - 1
            stack.append(current_index)
            continue

        if current_index is None:
            if not stripped:
                continue
            drafts.append(
                _SectionDraft(
                    title="Overview",
                    heading_level=1,
                    section_path=["Overview"],
                    parent_index=None,
                )
            )
            current_index = len(drafts) - 1

        drafts[current_index].lines.append((line_number, line))

    return drafts


def _finalize_sections(drafts: list[_SectionDraft], doc_id: str) -> list[ParsedSection]:
    section_by_index: dict[int, ParsedSection] = {}
    root_sections: list[ParsedSection] = []

    for index, draft in enumerate(drafts):
        content_lines = _trim_blank_edges(draft.lines)
        if not content_lines:
            continue

        text = "\n".join(line for _, line in content_lines).strip()
        line_start = content_lines[0][0]
        line_end = content_lines[-1][0]
        section = ParsedSection(
            section_id=_make_section_id(doc_id, draft.section_path, line_start),
            title=draft.title,
            heading_level=draft.heading_level,
            section_path=draft.section_path,
            text=text,
            line_start=line_start,
            line_end=line_end,
            children=[],
        )
        section_by_index[index] = section

        parent_index = draft.parent_index
        while parent_index is not None and parent_index not in section_by_index:
            parent_index = drafts[parent_index].parent_index
        if parent_index is None:
            root_sections.append(section)
        else:
            section_by_index[parent_index].children.append(section)

    return root_sections


def _trim_blank_edges(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    start = 0
    end = len(lines)
    while start < end and not lines[start][1].strip():
        start += 1
    while end > start and not lines[end - 1][1].strip():
        end -= 1
    return lines[start:end]


def _make_section_id(doc_id: str, section_path: list[str], line_start: int) -> str:
    return f"{doc_id}::sec-{normalize_slug(' '.join(section_path))}-{line_start:04d}"


def _first_heading_title(body: str) -> str | None:
    in_code_block = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
        if in_code_block:
            continue
        match = _HEADING_PATTERN.match(line)
        if match:
            return match.group(2).strip()
    return None


def _body_start_line(raw_text: str) -> int:
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return 1
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return index + 2
    return 1

