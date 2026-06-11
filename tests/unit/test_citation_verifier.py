from app.eval.citation_audit import verify_citations
from app.schemas.citation import Citation, CitationLocator
from tests.helpers import make_retrieved_chunk


def test_citation_verifier_accepts_citation_in_context() -> None:
    retrieved = [
        make_retrieved_chunk(
            "chunk-auth",
            "The refresh token endpoint is limited to 30 requests per minute.",
            doc_id="doc-auth",
        )
    ]
    citation = Citation(
        citation_id="CIT-0001",
        doc_id="doc-auth",
        chunk_id="chunk-auth",
        title="Auth",
        locator=CitationLocator(source_path="doc-auth"),
    )

    result = verify_citations(
        claims=["The refresh token endpoint is limited to 30 requests per minute."],
        citations=[citation],
        retrieved_chunks=retrieved,
    )

    assert result.citation_valid is True
    assert result.supports_core_claim is True


def test_citation_verifier_rejects_missing_chunk() -> None:
    citation = Citation(
        citation_id="CIT-0001",
        doc_id="doc-auth",
        chunk_id="missing",
        title="Auth",
        locator=CitationLocator(source_path="doc-auth"),
    )

    result = verify_citations(
        claims=["The refresh token endpoint is limited."],
        citations=[citation],
        retrieved_chunks=[],
    )

    assert result.citation_valid is False
    assert result.invalid_citations == ["CIT-0001"]

