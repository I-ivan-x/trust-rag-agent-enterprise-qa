from app.ingest.parser_markdown import parse_markdown_document
from app.schemas.document import RawDocument


def _flatten_titles(sections):
    titles = []
    for section in sections:
        titles.append(section.title)
        titles.extend(_flatten_titles(section.children))
    return titles


def test_markdown_parser_handles_front_matter_headings_and_code_blocks() -> None:
    raw_doc = RawDocument(
        source_path="docs/example.md",
        content="""---
doc_id: doc-example
title: Example Doc
doc_type: api_spec
status: active
version: v1
allowed_roles:
  - employee
---

Intro before heading.

# Example Doc
Body under H1.

## Details
Visible detail.

```
# Not A Heading
```

### Nested
Nested detail.
""",
    )

    parsed = parse_markdown_document(raw_doc)
    titles = _flatten_titles(parsed.sections)

    assert parsed.metadata.doc_id == "doc-example"
    assert "Overview" in titles
    assert "Example Doc" in titles
    assert "Details" in titles
    assert "Nested" in titles
    assert "# Not A Heading" in _section_by_title(parsed.sections, "Details").text
    assert "doc_id:" not in parsed.raw_text


def test_markdown_parser_generates_section_paths_and_line_numbers() -> None:
    raw_doc = RawDocument(
        source_path="docs/paths.md",
        content="""---
title: Path Doc
---
# Root

## Child
Child text.

### Leaf
Leaf text.
""",
    )

    parsed = parse_markdown_document(raw_doc)
    child = _section_by_title(parsed.sections, "Child")
    leaf = _section_by_title(parsed.sections, "Leaf")

    assert child.section_path == ["Root", "Child"]
    assert leaf.section_path == ["Root", "Child", "Leaf"]
    assert child.line_start is not None
    assert child.line_end is not None
    assert child.line_start <= child.line_end


def test_markdown_parser_keeps_overview_and_excludes_yaml_from_sections() -> None:
    raw_doc = RawDocument(
        source_path="docs/overview.md",
        content="""---
title: Overview Doc
---
Preface text.

# Main
Main text.
""",
    )

    parsed = parse_markdown_document(raw_doc)
    overview = parsed.sections[0]

    assert overview.title == "Overview"
    assert overview.text == "Preface text."
    assert "---" not in overview.text
    assert "title:" not in overview.text


def _section_by_title(sections, title):
    for section in sections:
        if section.title == title:
            return section
        try:
            return _section_by_title(section.children, title)
        except AssertionError:
            pass
    raise AssertionError(f"section not found: {title}")

