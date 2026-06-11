# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
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
        chunk_titles = _titles_for_cases(cases)
        report = _check_cases(cases, chunk_titles)
        if update_cases:
            write_eval_cases(input_path, cases)
        return _write_reports(report)

    splits = [EvalSplit(split)] if split is not None else list(EvalSplit)
    all_reports = []
    for eval_split in splits:
        path = eval_path_for_split(eval_split)
        cases = load_eval_cases(eval_split)
        chunk_titles = doc_titles_by_id(load_chunks_for_split(eval_split))
        split_report = _check_cases(cases, chunk_titles)
        split_report["path"] = path.as_posix()
        all_reports.append(split_report)
        if update_cases:
            write_eval_cases(path, cases)

    combined = _combine_reports(all_reports)
    return _write_reports(combined)


def _check_cases(cases: list[EvalCase], doc_titles: dict[str, str]) -> dict[str, Any]:
    flags: list[dict[str, Any]] = []
    split = cases[0].eval_split.value if cases else "unknown"
    low_overlap = 0
    for case in cases:
        titles = [doc_titles.get(doc_id, doc_id) for doc_id in case.gold_doc_ids]
        score = title_overlap_score(case.query, titles)
        case.title_overlap_score = score
        if score < 0.3:
            low_overlap += 1
        if score > 0.6:
            flags.append(
                {
                    "case_id": case.case_id,
                    "split": case.eval_split.value,
                    "flag_type": "high_title_overlap",
                    "score": score,
                }
            )
        copy_score = _answer_copy_score(case.reference_answer, titles)
        if copy_score > 0.8:
            flags.append(
                {
                    "case_id": case.case_id,
                    "split": case.eval_split.value,
                    "flag_type": "answer_copy_similarity",
                    "score": round(copy_score, 4),
                }
            )

    low_overlap_ratio = low_overlap / len(cases) if cases else 0.0
    if split == "external" and low_overlap_ratio < 0.4:
        flags.append(
            {
                "case_id": "__split__",
                "split": split,
                "flag_type": "external_low_overlap_ratio_below_40_percent",
                "score": round(low_overlap_ratio, 4),
            }
        )
    return {
        "split": split,
        "case_count": len(cases),
        "low_title_overlap_ratio": round(low_overlap_ratio, 4),
        "flags": flags,
    }


def _combine_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    flags = [flag for report in reports for flag in report["flags"]]
    return {
        "case_count": sum(report["case_count"] for report in reports),
        "splits": reports,
        "flags": flags,
        "passed": not flags,
    }


def _write_reports(report: dict[str, Any]) -> dict[str, Any]:
    report = {**report, "passed": not report.get("flags")}
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
        "",
        "## Flags",
        "",
    ]
    for flag in report.get("flags", []):
        lines.append(
            f"- {flag.get('split')} / {flag.get('case_id')}: "
            f"{flag.get('flag_type')} ({flag.get('score')})"
        )
    if not report.get("flags"):
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _answer_copy_score(reference_answer: str | None, titles: list[str]) -> float:
    if not reference_answer or not titles:
        return 0.0
    haystack = " ".join(titles).lower()
    return SequenceMatcher(None, reference_answer.lower(), haystack).ratio()


def _titles_for_cases(cases: list[EvalCase]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for eval_split in {case.eval_split for case in cases}:
        titles.update(doc_titles_by_id(load_chunks_for_split(eval_split)))
    return titles


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

