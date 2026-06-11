from pathlib import Path

from app.core.enums import AccessLevel, CorpusSource, DocumentStatus
from app.index.keyword_store import KeywordStore
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


def test_whoosh_index_search_and_filters(tmp_path: Path) -> None:
    store = KeywordStore(tmp_path / "whoosh")
    chunks = [
        _chunk(
            chunk_id="doc-a::chunk-0000",
            text="The refresh token endpoint is limited to 30 requests per minute.",
            status=DocumentStatus.active,
            access_level=AccessLevel.internal,
            corpus_source=CorpusSource.synthetic_fixture,
        ),
        _chunk(
            chunk_id="doc-b::chunk-0000",
            doc_id="doc-b",
            text="Admin keys must be rotated every 90 days.",
            status=DocumentStatus.active,
            access_level=AccessLevel.restricted,
            corpus_source=CorpusSource.synthetic_fixture,
        ),
        _chunk(
            chunk_id="doc-c::chunk-0000",
            doc_id="doc-c",
            text="Deprecated token lifetime was 60 minutes.",
            status=DocumentStatus.deprecated,
            access_level=AccessLevel.internal,
            corpus_source=CorpusSource.synthetic_fixture,
        ),
    ]

    store.recreate_index()
    store.index_chunks(chunks)

    assert store.count() == 3
    results = store.search("refresh token", top_k=5)
    assert results
    assert isinstance(results[0], RetrievedChunk)
    assert results[0].keyword_score is not None

    active_results = store.search("token", top_k=5, filters={"status": "active"})
    assert all(result.chunk.status == DocumentStatus.active for result in active_results)

    restricted_results = store.search(
        "keys",
        top_k=5,
        filters={"access_level": "restricted"},
    )
    assert restricted_results[0].chunk.access_level == AccessLevel.restricted

    corpus_results = store.search(
        "token",
        top_k=5,
        filters={"corpus_source": "synthetic_fixture"},
    )
    assert corpus_results


def _chunk(
    chunk_id: str,
    text: str,
    doc_id: str = "doc-a",
    status: DocumentStatus = DocumentStatus.active,
    access_level: AccessLevel = AccessLevel.internal,
    corpus_source: CorpusSource = CorpusSource.synthetic_fixture,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        chunk_index=0,
        text=text,
        section_path=["Doc", "Section"],
        heading_level=2,
        token_count=10,
        char_count=len(text),
        line_start=1,
        line_end=1,
        parent_section_id="sec-1",
        status=status,
        version="v1",
        allowed_roles=["employee"],
        access_level=access_level,
        tags=["test"],
        corpus_source=corpus_source,
    )

