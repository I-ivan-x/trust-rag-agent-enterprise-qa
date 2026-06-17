from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.enums import CorpusSource, EvalSplit
from app.schemas.chunk import Chunk
from app.schemas.eval import EvalCase

_CASE_FILE_BY_SPLIT = {
    EvalSplit.fixture: "fixture_eval.jsonl",
    EvalSplit.external: "external_eval.jsonl",
    EvalSplit.hard_negative: "hard_negative_eval.jsonl",
    EvalSplit.obfuscated: "obfuscated_eval.jsonl",
    EvalSplit.redteam: "redteam_eval.jsonl",
}

_CHUNK_FILE_BY_SPLIT = {
    EvalSplit.fixture: Path("data/generated/chunks.jsonl"),
    EvalSplit.external: Path("data/generated/public/chunks.jsonl"),
    EvalSplit.hard_negative: Path("data/generated/hard_negative/chunks.jsonl"),
    EvalSplit.obfuscated: Path("data/generated/public/chunks.jsonl"),
    EvalSplit.redteam: Path("data/generated/redteam/chunks.jsonl"),
}

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "can",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
}


def eval_path_for_split(split: EvalSplit, base_dir: Path | None = None) -> Path:
    base = base_dir or get_settings().gold_eval_dir
    return base / _CASE_FILE_BY_SPLIT[split]


def chunk_path_for_split(split: EvalSplit) -> Path:
    return _CHUNK_FILE_BY_SPLIT[split]


def load_eval_cases(
    split: EvalSplit | str | None = None,
    *,
    base_dir: Path | None = None,
    input_path: Path | None = None,
) -> list[EvalCase]:
    if input_path is not None:
        return [EvalCase.model_validate(record) for record in read_jsonl(input_path)]
    if split is None:
        cases: list[EvalCase] = []
        for eval_split in EvalSplit:
            path = eval_path_for_split(eval_split, base_dir)
            if path.exists():
                cases.extend(load_eval_cases(eval_split, base_dir=base_dir))
        return cases
    eval_split = EvalSplit(split)
    return [
        EvalCase.model_validate(record)
        for record in read_jsonl(eval_path_for_split(eval_split, base_dir))
    ]


def write_eval_cases(path: Path, cases: Iterable[EvalCase]) -> None:
    write_jsonl(
        path,
        [
            case.model_dump(
                mode="json",
                by_alias=True,
                exclude={"must_cite"},
                exclude_none=False,
            )
            for case in cases
        ],
    )


def load_chunks_for_split(split: EvalSplit | str, path: Path | None = None) -> list[Chunk]:
    selected_path = path or chunk_path_for_split(EvalSplit(split))
    return [Chunk.model_validate(record) for record in read_jsonl(selected_path)]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    rows = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def case_corpus_source(split: EvalSplit) -> CorpusSource:
    if split is EvalSplit.fixture:
        return CorpusSource.synthetic_fixture
    if split is EvalSplit.hard_negative:
        return CorpusSource.hard_negative
    if split is EvalSplit.redteam:
        return CorpusSource.redteam_injection
    return CorpusSource.public_external


def title_overlap_score(query: str, titles: Iterable[str]) -> float:
    query_terms = set(terms(query))
    if not query_terms:
        return 0.0
    title_terms: set[str] = set()
    for title in titles:
        title_terms.update(terms(title))
    return round(len(query_terms & title_terms) / len(query_terms), 4)


def terms(text: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return [term for term in normalized.split() if term and term not in _STOPWORDS]


def first_sentence(text: str, *, max_chars: int = 240) -> str:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    if len(sentence) <= max_chars:
        return sentence
    return sentence[: max_chars - 3].rstrip() + "..."


def doc_titles_by_id(chunks: Iterable[Chunk]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for chunk in chunks:
        if chunk.doc_id not in titles:
            titles[chunk.doc_id] = chunk.section_path[0] if chunk.section_path else chunk.doc_id
    return titles

