from app.core.enums import AccessLevel, CorpusSource, DocumentStatus, MetadataOrigin
from app.ingest.chunker import chunk_parsed_document
from app.ingest.parser_markdown import parse_markdown_document
from app.schemas.chunk import ChunkConfig
from app.schemas.document import DocumentMetadata, ParsedDocument, ParsedSection, RawDocument


def _metadata() -> DocumentMetadata:
    return DocumentMetadata(
        doc_id="doc-test",
        title="Test Doc",
        doc_type="api_spec",
        status=DocumentStatus.active,
        version="v1",
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
        tags=["auth"],
        source_path="data/sample_corpus/test.md",
        corpus_source=CorpusSource.synthetic_fixture,
        metadata_origin=MetadataOrigin.native,
        conflict_group_id="auth-token-lifetime",
        is_authoritative=True,
    )


def test_short_section_generates_one_chunk() -> None:
    parsed = ParsedDocument(
        metadata=_metadata(),
        sections=[
            ParsedSection(
                section_id="sec-1",
                title="Short",
                heading_level=2,
                section_path=["Test Doc", "Short"],
                text="Short section text.",
                line_start=3,
                line_end=3,
            )
        ],
        raw_text="Short section text.",
    )

    chunks = chunk_parsed_document(parsed, ChunkConfig(chunk_max_tokens=50, chunk_overlap_tokens=5))

    assert len(chunks) == 1
    assert chunks[0].chunk_id == "doc-test::chunk-0000"


def test_long_section_splits_and_chunk_ids_are_stable() -> None:
    long_text = "\n\n".join(
        [
            "alpha beta gamma delta epsilon zeta eta theta iota kappa",
            "lambda mu nu xi omicron pi rho sigma tau upsilon",
            "phi chi psi omega alpha beta gamma delta epsilon zeta",
        ]
    )
    parsed = ParsedDocument(
        metadata=_metadata(),
        sections=[
            ParsedSection(
                section_id="sec-long",
                title="Long",
                heading_level=2,
                section_path=["Test Doc", "Long"],
                text=long_text,
                line_start=5,
                line_end=9,
            )
        ],
        raw_text=long_text,
    )

    chunks = chunk_parsed_document(parsed, ChunkConfig(chunk_max_tokens=12, chunk_overlap_tokens=2))

    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert [chunk.chunk_id for chunk in chunks] == [
        f"doc-test::chunk-{index:04d}" for index in range(len(chunks))
    ]
    repeated_chunks = chunk_parsed_document(
        parsed,
        ChunkConfig(chunk_max_tokens=12, chunk_overlap_tokens=2),
    )
    assert repeated_chunks == chunks


def test_chunk_metadata_is_inherited_and_empty_chunks_are_skipped() -> None:
    parsed = ParsedDocument(
        metadata=_metadata(),
        sections=[
            ParsedSection(
                section_id="sec-empty",
                title="Empty",
                heading_level=2,
                section_path=["Test Doc", "Empty"],
                text="   ",
                line_start=2,
                line_end=2,
            ),
            ParsedSection(
                section_id="sec-real",
                title="Real",
                heading_level=2,
                section_path=["Test Doc", "Real"],
                text="Real content.",
                line_start=4,
                line_end=4,
            ),
        ],
        raw_text="Real content.",
    )

    chunks = chunk_parsed_document(parsed)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.access_level == AccessLevel.restricted
    assert chunk.corpus_source == CorpusSource.synthetic_fixture
    assert chunk.metadata_origin == MetadataOrigin.native
    assert chunk.conflict_group_id == "auth-token-lifetime"
    assert chunk.is_authoritative is True
    assert chunk.allowed_roles == ["security_admin"]


def test_front_matter_does_not_enter_chunk_text() -> None:
    parsed = parse_markdown_document(
        raw_doc=RawDocument(
            source_path="docs/frontmatter.md",
            content="""---
doc_id: doc-frontmatter
title: Frontmatter
doc_type: handbook
status: active
version: v1
---

# Main
Visible body.
""",
        )
    )

    chunks = chunk_parsed_document(parsed)

    assert chunks
    assert all("---" not in chunk.text for chunk in chunks)
    assert all("doc_id:" not in chunk.text for chunk in chunks)
