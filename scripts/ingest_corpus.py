# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingest.chunker import chunk_documents
from app.ingest.loader import load_corpus
from app.ingest.metadata_overlay import apply_metadata_overlay, load_metadata_overlay
from app.ingest.parser_markdown import parse_markdown_document
from app.ingest.parser_text import parse_text_document
from app.schemas.chunk import Chunk
from app.schemas.document import ParsedDocument, RawDocument
from app.schemas.eval import EvalCase


def run_ingest(
    input_dir: Path,
    output_dir: Path,
    eval_path: Path | None = None,
    review_path: Path | None = Path("docs/EVAL_CASE_REVIEW_WEEK1.md"),
    overlay_path: Path | None = None,
    include_redteam: bool = False,
    redteam_input_dir: Path = Path("data/redteam_corpus"),
) -> dict[str, Any]:
    raw_documents = load_corpus(input_dir)
    redteam_documents: list[RawDocument] = []
    if include_redteam:
        redteam_documents = load_corpus(redteam_input_dir)
        raw_documents = [*raw_documents, *redteam_documents]
    parsed_documents = [_parse_raw_document(raw_doc) for raw_doc in raw_documents]
    overlay = load_metadata_overlay(overlay_path)
    overlay_summary = apply_metadata_overlay(
        parsed_documents,
        overlay,
        corpus_root=input_dir,
    )
    chunks = chunk_documents(parsed_documents)

    output_dir.mkdir(parents=True, exist_ok=True)
    documents_output_path = output_dir / "documents.jsonl"
    chunks_output_path = output_dir / "chunks.jsonl"
    chunk_manifest_output_path = output_dir / "chunk_manifest.jsonl"

    write_documents_jsonl(documents_output_path, parsed_documents)
    write_chunks_jsonl(chunks_output_path, chunks)
    write_chunk_manifest_jsonl(chunk_manifest_output_path, chunks)

    backfill_details: dict[str, Any] = {"updated": False, "cases": []}
    if eval_path is not None and eval_path.exists():
        backfill_details = backfill_demo_eval_gold_chunks(eval_path, chunks)
        if review_path is not None:
            write_eval_case_review(review_path, eval_path, chunks)

    return {
        "loaded_files": len(raw_documents),
        "loaded_fixture_files": len(raw_documents) - len(redteam_documents),
        "loaded_redteam_files": len(redteam_documents),
        "include_redteam": include_redteam,
        "parsed_documents": len(parsed_documents),
        "generated_chunks": len(chunks),
        "documents_output_path": documents_output_path.as_posix(),
        "chunks_output_path": chunks_output_path.as_posix(),
        "chunk_manifest_output_path": chunk_manifest_output_path.as_posix(),
        "overlay_applied": overlay_summary.overlay_applied,
        "overlay_modified_count": overlay_summary.overlay_modified_count,
        "restricted_or_confidential_ratio": overlay_summary.restricted_or_confidential_ratio,
        "deprecated_ratio": overlay_summary.deprecated_ratio,
        "demo_eval_backfilled": backfill_details["updated"],
        "demo_eval_backfill_details": backfill_details["cases"],
    }


def write_documents_jsonl(path: Path, parsed_documents: list[ParsedDocument]) -> None:
    records = []
    for parsed_doc in parsed_documents:
        metadata = parsed_doc.metadata
        records.append(
            {
                "doc_id": metadata.doc_id,
                "title": metadata.title,
                "doc_type": metadata.doc_type.value,
                "status": metadata.status.value,
                "version": metadata.version,
                "source_path": metadata.source_path,
                "corpus_source": metadata.corpus_source.value,
                "metadata_origin": metadata.metadata_origin.value,
                "overlay_applied": metadata.metadata_origin.value == "overlay",
                "section_count": _section_count(parsed_doc.sections),
            }
        )
    _write_jsonl(path, records)


def write_chunks_jsonl(path: Path, chunks: list[Chunk]) -> None:
    _write_jsonl(path, [chunk.model_dump(mode="json") for chunk in chunks])


def write_chunk_manifest_jsonl(path: Path, chunks: list[Chunk]) -> None:
    _write_jsonl(
        path,
        [
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "chunk_index": chunk.chunk_index,
                "section_path": chunk.section_path,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "status": chunk.status.value,
                "access_level": chunk.access_level.value,
                "corpus_source": chunk.corpus_source.value,
                "hard_negative_group_id": chunk.hard_negative_group_id,
                "metadata_origin": chunk.metadata_origin.value,
                "overlay_applied": chunk.metadata_origin.value == "overlay",
            }
            for chunk in chunks
        ],
    )


def backfill_demo_eval_gold_chunks(eval_path: Path, chunks: list[Chunk]) -> dict[str, Any]:
    cases = _read_eval_cases(eval_path)
    details: list[dict[str, Any]] = []
    changed = False

    for case in cases:
        selected = _select_gold_chunks_for_case(case, chunks)
        selected_ids = [chunk.chunk_id for chunk in selected]
        if case.gold_chunk_ids != selected_ids:
            case.gold_chunk_ids = selected_ids
            changed = True
        details.append(
            {
                "case_id": case.case_id,
                "selected_chunk_ids": selected_ids,
                "candidates": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "doc_id": chunk.doc_id,
                        "section_path": chunk.section_path,
                    }
                    for chunk in selected
                ],
            }
        )

    _write_jsonl(eval_path, [case.model_dump(mode="json") for case in cases])
    return {"updated": changed, "cases": details}


def write_eval_case_review(eval_review_path: Path, eval_path: Path, chunks: list[Chunk]) -> None:
    eval_review_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    lines = [
        "# Week 1 Demo Eval Case Review",
        "",
        "This file is a Week 1 review aid for Owner/Claude. It is not a formal "
        "evaluation report and must not be used as headline metrics.",
        "",
    ]

    for case in _read_eval_cases(eval_path):
        lines.extend(
            [
                f"## {case.case_id}",
                "",
                f"- query: {case.query}",
                f"- expected_behavior: {case.expected_behavior.value}",
                f"- gold_doc_ids: {case.gold_doc_ids}",
                f"- gold_chunk_ids: {case.gold_chunk_ids}",
                "",
            ]
        )
        if not case.gold_chunk_ids:
            lines.extend(["Needs Owner/Claude confirmation: no supporting chunk is expected.", ""])
            continue

        for chunk_id in case.gold_chunk_ids:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                lines.extend(
                    [
                        f"### {chunk_id}",
                        "",
                        "Needs Owner/Claude confirmation: chunk ID was not found in "
                        "generated chunks.",
                        "",
                    ]
                )
                continue
            preview = chunk.text[:200].replace("\n", " ")
            lines.extend(
                [
                    f"### {chunk.chunk_id}",
                    "",
                    f"- doc_id: {chunk.doc_id}",
                    f"- section_path: {chunk.section_path}",
                    f"- text_preview: {preview}",
                    "",
                ]
            )
        lines.extend(["Needs Owner/Claude confirmation: verify gold chunk relevance.", ""])

    eval_review_path.write_text("\n".join(lines), encoding="utf-8")


def _parse_raw_document(raw_doc: RawDocument) -> ParsedDocument:
    suffix = Path(raw_doc.source_path).suffix.lower()
    if suffix == ".txt":
        return parse_text_document(raw_doc)
    return parse_markdown_document(raw_doc)


def _select_gold_chunks_for_case(case: EvalCase, chunks: list[Chunk]) -> list[Chunk]:
    if case.expected_behavior.value == "refuse_no_evidence" or not case.gold_doc_ids:
        return []

    candidates = [chunk for chunk in chunks if chunk.doc_id in case.gold_doc_ids]
    if case.expected_behavior.value == "refuse_permission":
        restricted = [chunk for chunk in candidates if chunk.access_level.value == "restricted"]
        return _top_chunks(case.query, restricted or candidates, limit=1)

    if case.expected_behavior.value == "report_conflict":
        active_candidates = [
            chunk
            for chunk in candidates
            if chunk.status.value == "active" and chunk.conflict_group_id is not None
        ]
        selected: list[Chunk] = []
        for doc_id in case.gold_doc_ids:
            doc_candidates = [chunk for chunk in active_candidates if chunk.doc_id == doc_id]
            selected.extend(_top_chunks(case.query, doc_candidates, limit=1))
        return selected

    return _top_chunks(case.query, candidates, limit=1)


def _top_chunks(query: str, chunks: list[Chunk], limit: int) -> list[Chunk]:
    scored = sorted(
        ((chunk, _keyword_score(query, chunk)) for chunk in chunks),
        key=lambda item: (-item[1], item[0].doc_id, item[0].chunk_index),
    )
    positive_matches = [chunk for chunk, score in scored[:limit] if score > 0]
    return positive_matches or [chunk for chunk, _ in scored[:limit]]


def _keyword_score(query: str, chunk: Chunk) -> int:
    query_terms = _terms(query)
    haystack = " ".join([chunk.doc_id, " ".join(chunk.section_path), chunk.text]).lower()
    section_tail = chunk.section_path[-1].lower() if chunk.section_path else ""
    text = chunk.text.lower()
    score = sum(1 for term in query_terms if term in haystack)
    score += sum(2 for term in query_terms if term in section_tail)
    score += sum(1 for term in query_terms if term in text)
    return score


def _terms(text: str) -> set[str]:
    stopwords = {
        "the",
        "is",
        "a",
        "an",
        "or",
        "and",
        "what",
        "how",
        "did",
        "in",
        "to",
        "per",
    }
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {term for term in normalized.split() if term not in stopwords}


def _read_eval_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvalCase.model_validate_json(line))
    return cases


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _section_count(sections: list[Any]) -> int:
    return sum(1 + _section_count(section.children) for section in sections)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Week 1 sample corpus into JSONL files.")
    parser.add_argument("--input", type=Path, default=Path("data/sample_corpus"))
    parser.add_argument("--output", type=Path, default=Path("data/generated"))
    parser.add_argument("--corpus", choices=["sample", "public", "hard_negative"], default="sample")
    parser.add_argument("--eval", type=Path, default=None)
    parser.add_argument("--overlay", type=Path, default=None)
    parser.add_argument(
        "--include-redteam",
        action="store_true",
        help="Include data/redteam_corpus in addition to the selected fixture corpus.",
    )
    parser.add_argument("--redteam-input", type=Path, default=Path("data/redteam_corpus"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_ingest(
        input_dir=args.input,
        output_dir=args.output,
        eval_path=args.eval or _default_eval_path(args.input),
        overlay_path=args.overlay,
        include_redteam=args.include_redteam,
        redteam_input_dir=args.redteam_input,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _default_eval_path(input_dir: Path) -> Path | None:
    if input_dir.as_posix().rstrip("/") == Path("data/sample_corpus").as_posix():
        return Path("data/gold_eval/demo_eval.jsonl")
    return None


if __name__ == "__main__":
    main()
