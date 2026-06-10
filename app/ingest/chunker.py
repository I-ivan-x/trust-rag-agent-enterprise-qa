from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.ids import make_chunk_id
from app.schemas.chunk import Chunk, ChunkConfig
from app.schemas.document import DocumentMetadata, ParsedDocument, ParsedSection

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass
class _ChunkSegment:
    text: str
    section_path: list[str]
    heading_level: int | None
    line_start: int | None
    line_end: int | None
    parent_section_id: str | None


def estimate_token_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    tokens = _TOKEN_PATTERN.findall(stripped)
    if tokens:
        return len(tokens)
    return max(1, len(stripped) // 4)


def chunk_parsed_document(
    parsed_doc: ParsedDocument,
    config: ChunkConfig | None = None,
) -> list[Chunk]:
    chunk_config = config or ChunkConfig()
    segments: list[_ChunkSegment] = []
    for section in _flatten_sections(parsed_doc.sections):
        segments.extend(_split_section(section, chunk_config))

    chunks: list[Chunk] = []
    for index, segment in enumerate(segment for segment in segments if segment.text.strip()):
        chunks.append(_build_chunk(parsed_doc.metadata, segment, index))
    return chunks


def chunk_documents(
    parsed_docs: list[ParsedDocument],
    config: ChunkConfig | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for parsed_doc in parsed_docs:
        chunks.extend(chunk_parsed_document(parsed_doc, config=config))
    return chunks


def _split_section(section: ParsedSection, config: ChunkConfig) -> list[_ChunkSegment]:
    text = section.text.strip()
    if not text:
        return []

    if estimate_token_count(text) <= config.chunk_max_tokens:
        return [
            _ChunkSegment(
                text=text,
                section_path=section.section_path,
                heading_level=section.heading_level,
                line_start=section.line_start,
                line_end=section.line_end,
                parent_section_id=section.section_id,
            )
        ]

    paragraph_segments = _split_section_by_paragraph(section)
    packed_segments = _pack_paragraphs(paragraph_segments, config)
    if config.chunk_overlap_tokens <= 0:
        return packed_segments
    return _apply_word_overlap(packed_segments, config)


def _split_section_by_paragraph(section: ParsedSection) -> list[_ChunkSegment]:
    paragraphs: list[_ChunkSegment] = []
    current_lines: list[tuple[int | None, str]] = []
    base_line = section.line_start or 1

    for offset, line in enumerate(section.text.splitlines()):
        line_number = base_line + offset
        if not line.strip():
            _flush_paragraph(paragraphs, current_lines, section)
            current_lines = []
            continue
        current_lines.append((line_number, line))
    _flush_paragraph(paragraphs, current_lines, section)
    return paragraphs


def _flush_paragraph(
    paragraphs: list[_ChunkSegment],
    lines: list[tuple[int | None, str]],
    section: ParsedSection,
) -> None:
    if not lines:
        return
    text = "\n".join(line for _, line in lines).strip()
    if not text:
        return
    paragraphs.append(
        _ChunkSegment(
            text=text,
            section_path=section.section_path,
            heading_level=section.heading_level,
            line_start=lines[0][0],
            line_end=lines[-1][0],
            parent_section_id=section.section_id,
        )
    )


def _pack_paragraphs(paragraphs: list[_ChunkSegment], config: ChunkConfig) -> list[_ChunkSegment]:
    packed: list[_ChunkSegment] = []
    current: list[_ChunkSegment] = []
    current_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = estimate_token_count(paragraph.text)
        if paragraph_tokens > config.chunk_max_tokens:
            if current:
                packed.append(_merge_segments(current))
                current = []
                current_tokens = 0
            packed.extend(_split_long_segment(paragraph, config))
            continue

        if current and current_tokens + paragraph_tokens > config.chunk_max_tokens:
            packed.append(_merge_segments(current))
            current = [paragraph]
            current_tokens = paragraph_tokens
        else:
            current.append(paragraph)
            current_tokens += paragraph_tokens

    if current:
        packed.append(_merge_segments(current))
    return packed


def _split_long_segment(segment: _ChunkSegment, config: ChunkConfig) -> list[_ChunkSegment]:
    max_chars = max(120, config.chunk_max_tokens * 6)
    overlap_chars = min(max_chars // 4, max(0, config.chunk_overlap_tokens * 6))
    text = segment.text.strip()
    parts: list[_ChunkSegment] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        part = text[start:end].strip()
        if part:
            parts.append(
                _ChunkSegment(
                    text=part,
                    section_path=segment.section_path,
                    heading_level=segment.heading_level,
                    line_start=segment.line_start,
                    line_end=segment.line_end,
                    parent_section_id=segment.parent_section_id,
                )
            )
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return parts


def _merge_segments(segments: list[_ChunkSegment]) -> _ChunkSegment:
    first = segments[0]
    return _ChunkSegment(
        text="\n\n".join(segment.text for segment in segments).strip(),
        section_path=first.section_path,
        heading_level=first.heading_level,
        line_start=first.line_start,
        line_end=segments[-1].line_end,
        parent_section_id=first.parent_section_id,
    )


def _apply_word_overlap(segments: list[_ChunkSegment], config: ChunkConfig) -> list[_ChunkSegment]:
    if len(segments) <= 1:
        return segments

    overlap_size = min(config.chunk_overlap_tokens, max(1, config.chunk_max_tokens // 5))
    overlapped = [segments[0]]
    for previous, current in zip(segments, segments[1:], strict=False):
        words = previous.text.split()
        overlap = " ".join(words[-overlap_size:])
        text = f"{overlap}\n\n{current.text}".strip() if overlap else current.text
        overlapped.append(
            _ChunkSegment(
                text=text,
                section_path=current.section_path,
                heading_level=current.heading_level,
                line_start=current.line_start,
                line_end=current.line_end,
                parent_section_id=current.parent_section_id,
            )
        )
    return overlapped


def _build_chunk(metadata: DocumentMetadata, segment: _ChunkSegment, chunk_index: int) -> Chunk:
    text = segment.text.strip()
    return Chunk(
        chunk_id=make_chunk_id(metadata.doc_id, chunk_index),
        doc_id=metadata.doc_id,
        chunk_index=chunk_index,
        text=text,
        section_path=segment.section_path,
        heading_level=segment.heading_level,
        token_count=estimate_token_count(text),
        char_count=len(text),
        line_start=segment.line_start,
        line_end=segment.line_end,
        parent_section_id=segment.parent_section_id,
        status=metadata.status,
        version=metadata.version,
        allowed_roles=metadata.allowed_roles,
        access_level=metadata.access_level,
        tags=metadata.tags,
        corpus_source=metadata.corpus_source,
        source_origin=metadata.source_origin,
        source_license_note=metadata.source_license_note,
        hard_negative_group_id=metadata.hard_negative_group_id,
        metadata_origin=metadata.metadata_origin,
        conflict_group_id=metadata.conflict_group_id,
        is_authoritative=metadata.is_authoritative,
    )


def _flatten_sections(sections: list[ParsedSection]) -> list[ParsedSection]:
    flattened: list[ParsedSection] = []
    for section in sections:
        flattened.append(section)
        flattened.extend(_flatten_sections(section.children))
    return flattened
