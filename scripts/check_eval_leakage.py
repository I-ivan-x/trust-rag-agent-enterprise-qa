# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.enums import EvalSplit
from app.eval.dataset import (
    doc_titles_by_id,
    eval_path_for_split,
    load_chunks_for_split,
    load_eval_cases,
    terms,
    title_overlap_score,
    write_eval_cases,
)
from app.schemas.eval import EvalCase

LEAKAGE_REPORT_JSON = Path("data/eval_runs/leakage_report.json")
LEAKAGE_REPORT_MD = Path("docs/EVAL_LEAKAGE_REPORT.md")


def check_leakage(
    *,
    split: EvalSplit | str | None = None,
    input_path: Path | None = None,
    update_cases: bool = True,
) -> dict[str, Any]:
    if input_path is not None:
        cases = load_eval_cases(input_path=input_path)
        chunks = _chunks_for_cases(cases)
        report = _check_cases(cases, chunks)
        if update_cases:
            write_eval_cases(input_path, cases)
        return _write_reports(report)

    splits = [EvalSplit(split)] if split is not None else list(EvalSplit)
    all_reports = []
    for eval_split in splits:
        path = eval_path_for_split(eval_split)
        cases = load_eval_cases(eval_split)
        chunks = load_chunks_for_split(eval_split)
        split_report = _check_cases(cases, chunks)
        split_report["path"] = path.as_posix()
        all_reports.append(split_report)
        if update_cases:
            write_eval_cases(path, cases)

    combined = _combine_reports(all_reports)
    return _write_reports(combined)


def _check_cases(cases: list[EvalCase], chunks: list[Any]) -> dict[str, Any]:
    flags: list[dict[str, Any]] = []
    split = cases[0].eval_split.value if cases else "unknown"
    doc_titles = doc_titles_by_id(chunks)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    chunks_by_doc: dict[str, list[Any]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_doc[chunk.doc_id].append(chunk)
    low_overlap = 0
    for case in cases:
        titles = [doc_titles.get(doc_id, doc_id) for doc_id in case.gold_doc_ids]
        score = title_overlap_score(case.query, titles)
        case.title_overlap_score = score
        if score < 0.3:
            low_overlap += 1
        if score > 0.6:
            flags.append(
                _flag(
                    case_id=case.case_id,
                    split=case.eval_split.value,
                    flag_type="high_title_overlap",
                    score=score,
                    blocking=case.eval_split is not EvalSplit.hard_negative,
                )
            )

        gold_chunks = [
            chunks_by_id[chunk_id] for chunk_id in case.gold_chunk_ids if chunk_id in chunks_by_id
        ]
        missing_gold_chunk_ids = [
            chunk_id for chunk_id in case.gold_chunk_ids if chunk_id not in chunks_by_id
        ]
        if missing_gold_chunk_ids:
            flags.append(
                _flag(
                    case_id=case.case_id,
                    split=case.eval_split.value,
                    flag_type="missing_gold_chunk",
                    score=len(missing_gold_chunk_ids),
                    details={"missing_gold_chunk_ids": missing_gold_chunk_ids},
                )
            )
        gold_content_chunks = _gold_content_chunks(case, gold_chunks, chunks_by_doc)
        if (
            not missing_gold_chunk_ids
            and gold_content_chunks
            and not _gold_content_overlap_terms(case.query, gold_content_chunks)
        ):
            flags.append(
                _flag(
                    case_id=case.case_id,
                    split=case.eval_split.value,
                    flag_type="no_retrievable_content",
                    score=0.0,
                )
            )
        copy_score = _answer_copy_score(case, gold_chunks)
        if copy_score > 0.8:
            flags.append(
                _flag(
                    case_id=case.case_id,
                    split=case.eval_split.value,
                    flag_type="answer_copy_similarity",
                    score=round(copy_score, 4),
                )
            )

    low_overlap_ratio = low_overlap / len(cases) if cases else 0.0
    if split == "external" and low_overlap_ratio < 0.4:
        flags.append(
            _flag(
                case_id="__split__",
                split=split,
                flag_type="external_low_overlap_ratio_below_40_percent",
                score=round(low_overlap_ratio, 4),
            )
        )
    return {
        "split": split,
        "case_count": len(cases),
        "low_title_overlap_ratio": round(low_overlap_ratio, 4),
        "flags": flags,
        "blocking_flags": _blocking_flags(flags),
        "passed": not _blocking_flags(flags),
    }


def _combine_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    flags = [flag for report in reports for flag in report["flags"]]
    blocking_flags = _blocking_flags(flags)
    return {
        "case_count": sum(report["case_count"] for report in reports),
        "splits": reports,
        "flags": flags,
        "blocking_flags": blocking_flags,
        "passed": not blocking_flags,
    }


def _write_reports(report: dict[str, Any]) -> dict[str, Any]:
    blocking_flags = _blocking_flags(report.get("flags", []))
    report = {**report, "blocking_flags": blocking_flags, "passed": not blocking_flags}
    LEAKAGE_REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    LEAKAGE_REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LEAKAGE_REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    LEAKAGE_REPORT_MD.write_text(_format_markdown(report), encoding="utf-8")
    return report


def _format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Eval Leakage Report",
        "",
        f"- passed: `{report.get('passed', False)}`",
        f"- case_count: `{report.get('case_count', 0)}`",
        f"- flags: `{len(report.get('flags', []))}`",
        f"- blocking_flags: `{len(report.get('blocking_flags', []))}`",
        "",
        "## Flags",
        "",
    ]
    for flag in report.get("flags", []):
        lines.append(
            f"- {flag.get('split')} / {flag.get('case_id')}: "
            f"{flag.get('flag_type')} ({flag.get('score')}, "
            f"blocking={flag.get('blocking', True)})"
        )
    if not report.get("flags"):
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _answer_copy_score(case: EvalCase, gold_chunks: list[Any]) -> float:
    candidates = [
        text for text in [case.reference_answer, *case.reference_claims] if text and text.strip()
    ]
    for chunk in gold_chunks:
        candidates.extend(_sentences(chunk.text))
    if not case.query or not candidates:
        return 0.0
    query = case.query.lower()
    return max(SequenceMatcher(None, query, candidate.lower()).ratio() for candidate in candidates)


def _gold_content_overlap_terms(query: str, gold_chunks: list[Any]) -> set[str]:
    query_terms = set(terms(query))
    if not query_terms:
        return set()
    gold_terms: set[str] = set()
    for chunk in gold_chunks:
        gold_terms.update(terms(chunk.text))
    return query_terms & gold_terms


def _gold_content_chunks(
    case: EvalCase,
    gold_chunks: list[Any],
    chunks_by_doc: dict[str, list[Any]],
) -> list[Any]:
    selected = {chunk.chunk_id: chunk for chunk in gold_chunks}
    for doc_id in case.gold_doc_ids:
        for chunk in chunks_by_doc.get(doc_id, []):
            selected.setdefault(chunk.chunk_id, chunk)
    return list(selected.values())


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in text.replace("\n", " ").split(".") if sentence.strip()]


def _flag(
    *,
    case_id: str,
    split: str,
    flag_type: str,
    score: float | int,
    blocking: bool = True,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    flag = {
        "case_id": case_id,
        "split": split,
        "flag_type": flag_type,
        "score": score,
        "blocking": blocking,
    }
    if details:
        flag.update(details)
    return flag


def _blocking_flags(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [flag for flag in flags if flag.get("blocking", True)]


def _chunks_for_cases(cases: list[EvalCase]) -> list[Any]:
    chunks: list[Any] = []
    for eval_split in {case.eval_split for case in cases}:
        chunks.extend(load_chunks_for_split(eval_split))
    return chunks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Week 5B eval leakage.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--split", choices=[split.value for split in EvalSplit])
    group.add_argument("--input", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = check_leakage(
        split=args.split,
        input_path=args.input,
        update_cases=True,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
