from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.eval.dataset import read_jsonl


def write_eval_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Evaluation Report",
        "",
        "> Week 5B repair note: Previous obfuscated/agentic smoke results generated before "
        "the expected_rewrite isolation fix are invalidated and must not be cited.",
        "",
        "Week 5B evaluation artifacts are present, but mock runs are smoke checks only.",
        "Headline metrics require real embedding, real reranker, and real LLM providers.",
        "expected_rewrite is informational only and is never used for retrieval or scoring.",
        "",
        "## Latest Local Run",
        "",
        f"- run_id: `{summary.get('run_id', 'n/a')}`",
        f"- split: `{summary.get('split', 'n/a')}`",
        f"- systems: `{', '.join(summary.get('systems', []))}`",
        f"- mode: `{summary.get('mode', 'n/a')}`",
        f"- headline_eligible: `{summary.get('headline_eligible', False)}`",
        f"- toy_retrieval: `{summary.get('toy_retrieval', False)}`",
        f"- unavailable_systems: `{summary.get('unavailable_systems', {})}`",
        "",
        "## Summary Metrics",
        "",
        "```json",
        json.dumps(
            summary.get("summary_metrics", {}),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## Data Notes",
        "",
        "- fixture split remains functional regression and is never headline.",
        "- hard_negative split is a retrieval/citation robustness slice.",
        "- obfuscated split compares final_gated and final_agentic behavior only.",
        "- citation audit is rule-based v1 and requires human sampling before claims.",
        "- external conflict cases use the existing active-active synthetic conflict group "
        "because the public FastAPI corpus has no native conflict_group_id overlay.",
        "",
        "## External Coverage",
        "",
        "```json",
        json.dumps(_external_coverage(), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _external_coverage() -> dict[str, Any]:
    path = Path("data/gold_eval/external_eval.jsonl")
    if not path.exists():
        return {"available": False}
    rows = read_jsonl(path)
    query_types = Counter(row["query_type"] for row in rows)
    behaviors = Counter(row["expected_behavior"] for row in rows)
    query_sources = Counter(row["query_source"] for row in rows)
    return {
        "available": True,
        "case_count": len(rows),
        "query_type_distribution": dict(sorted(query_types.items())),
        "expected_behavior_distribution": dict(sorted(behaviors.items())),
        "query_source_distribution": dict(sorted(query_sources.items())),
        "real_user_question_ratio": round(
            query_sources.get("real_user_question", 0) / len(rows),
            4,
        )
        if rows
        else 0.0,
    }


def write_failure_analysis(path: Path, failures: list[dict[str, Any]]) -> None:
    lines = [
        "# Failure Analysis",
        "",
        "This draft is generated from the latest local eval run.",
        "",
        f"Failure rows: {len(failures)}",
        "",
    ]
    for failure in failures[:25]:
        lines.extend(
            [
                f"## {failure.get('case_id')} / {failure.get('system_name')}",
                "",
                f"- reason: {failure.get('reason', 'n/a')}",
                f"- query: {failure.get('query', 'n/a')}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_citation_audit_doc(path: Path, audits: list[dict[str, Any]]) -> None:
    lines = [
        "# Citation Audit",
        "",
        "Rule-based v1 audit sample. This is not a human adjudication file.",
        "",
        f"Sample rows: {len(audits)}",
        "",
    ]
    invalid = [audit for audit in audits if not audit.get("citation_valid", True)]
    lines.extend(
        [
            f"- invalid citation rows: {len(invalid)}",
            "- manual review required before reporting headline citation quality.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
