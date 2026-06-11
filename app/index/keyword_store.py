from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from whoosh import index
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import ID, KEYWORD, NUMERIC, TEXT, Schema
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.query import Every

from app.core.config import get_settings
from app.core.enums import RetrievalSource
from app.schemas.chunk import Chunk
from app.schemas.retrieval import RetrievedChunk


class KeywordStore:
    def __init__(self, index_dir: Path | None = None) -> None:
        settings = get_settings()
        self.index_dir = Path(index_dir or settings.whoosh_index_dir)
        self.schema = Schema(
            chunk_id=ID(stored=True, unique=True),
            doc_id=ID(stored=True),
            chunk_index=NUMERIC(stored=True),
            text=TEXT(stored=True, analyzer=StemmingAnalyzer()),
            section_path_text=TEXT(stored=True, analyzer=StemmingAnalyzer()),
            status=ID(stored=True),
            access_level=ID(stored=True),
            corpus_source=ID(stored=True),
            source_origin=ID(stored=True),
            metadata_origin=ID(stored=True),
            hard_negative_group_id=ID(stored=True),
            conflict_group_id=ID(stored=True),
            version=ID(stored=True),
            allowed_roles=KEYWORD(stored=True, commas=True, lowercase=True),
            tags=KEYWORD(stored=True, commas=True, lowercase=True),
            chunk_json=TEXT(stored=True),
        )

    def recreate_index(self) -> None:
        if self.index_dir.exists():
            shutil.rmtree(self.index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        index.create_in(self.index_dir, self.schema)

    def index_chunks(self, chunks: list[Chunk]) -> None:
        ix = self._open_or_create_index()
        writer = ix.writer()
        try:
            for chunk in chunks:
                writer.update_document(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    section_path_text=" / ".join(chunk.section_path),
                    status=chunk.status.value,
                    access_level=chunk.access_level.value,
                    corpus_source=chunk.corpus_source.value,
                    source_origin=chunk.source_origin.value,
                    metadata_origin=chunk.metadata_origin.value,
                    hard_negative_group_id=chunk.hard_negative_group_id or "",
                    conflict_group_id=chunk.conflict_group_id or "",
                    version=chunk.version,
                    allowed_roles=",".join(chunk.allowed_roles),
                    tags=",".join(chunk.tags),
                    chunk_json=chunk.model_dump_json(),
                )
        finally:
            writer.commit()

    def search(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        if top_k <= 0:
            return []
        if not index.exists_in(self.index_dir):
            raise FileNotFoundError(
                f"Whoosh index does not exist at {self.index_dir}. Rebuild indexes first."
            )
        ix = index.open_dir(self.index_dir)
        with ix.searcher() as searcher:
            parsed_query = (
                MultifieldParser(
                    ["text", "section_path_text"],
                    schema=ix.schema,
                    group=OrGroup,
                ).parse(query)
                if query.strip()
                else Every()
            )
            raw_hits = searcher.search(parsed_query, limit=max(top_k * 5, top_k))
            results: list[RetrievedChunk] = []
            for hit in raw_hits:
                if not _matches_filters(hit, filters):
                    continue
                chunk = Chunk.model_validate_json(hit["chunk_json"])
                results.append(
                    RetrievedChunk(
                        chunk=chunk,
                        source=RetrievalSource.keyword,
                        keyword_score=float(hit.score),
                        rank=len(results) + 1,
                    )
                )
                if len(results) >= top_k:
                    break
            return results

    def count(self) -> int:
        if not index.exists_in(self.index_dir):
            return 0
        ix = index.open_dir(self.index_dir)
        with ix.searcher() as searcher:
            return int(searcher.doc_count_all())

    def _open_or_create_index(self) -> index.FileIndex:
        if index.exists_in(self.index_dir):
            return index.open_dir(self.index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        return index.create_in(self.index_dir, self.schema)


def _matches_filters(hit: Any, filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    for key in ("status", "access_level", "corpus_source", "doc_id"):
        if key not in filters or filters[key] is None:
            continue
        expected = filters[key]
        actual = hit.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True

