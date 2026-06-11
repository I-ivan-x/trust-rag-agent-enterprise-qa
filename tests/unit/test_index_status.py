from pathlib import Path

from app.index.index_status import get_index_status
from app.index.keyword_store import KeywordStore
from tests.unit.test_keyword_store import _chunk


def test_index_status_warns_when_chunks_file_missing(tmp_path: Path) -> None:
    status = get_index_status(
        chunks_path=tmp_path / "missing.jsonl",
        vector_store=_FailingVectorStore(),
        keyword_store=KeywordStore(tmp_path / "missing-whoosh"),
    )

    assert status.chunks_count == 0
    assert status.keyword_ready is False
    assert any("Chunks file does not exist" in warning for warning in status.warnings)


def test_index_status_reports_keyword_ready_and_qdrant_warning(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    chunk = _chunk("doc-a::chunk-0000", "refresh token rate limit")
    chunks_path.write_text(chunk.model_dump_json() + "\n", encoding="utf-8")

    store = KeywordStore(tmp_path / "whoosh")
    store.recreate_index()
    store.index_chunks([chunk])

    status = get_index_status(
        chunks_path=chunks_path,
        vector_store=_FailingVectorStore(),
        keyword_store=store,
    )

    assert status.keyword_ready is True
    assert status.keyword_count == 1
    assert status.vector_ready is False
    assert any("Qdrant status unavailable" in warning for warning in status.warnings)


class _FailingVectorStore:
    def count(self) -> int:
        raise RuntimeError("qdrant unavailable")

