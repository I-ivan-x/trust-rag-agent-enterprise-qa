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
        "> Pre-Week-6 obfuscated/agentic smoke results generated before the "
        "expected_rewrite isolation fix are invalidated and must not be cited.",
        "",
        "Mock runs are smoke checks only. Headline metrics require real embedding, "
        "real reranker, and a real LLM provider, and only count when "
        "`headline_eligible=true`.",
        "expected_rewrite is informational only and is never used for retrieval or scoring.",
        "",
        "## Latest Local Run",
        "",
        f"- run_id: `{summary.get('run_id', 'n/a')}`",
        f"- split: `{summary.get('split', 'n/a')}`",
        f"- systems: `{', '.join(summary.get('systems', []))}`",
        f"- mode: `{summary.get('mode', 'n/a')}`",
        f"- headline_eligible: `{summary.get('headline_eligible', False)}`",
        f"- headline_scope: `{summary.get('headline_scope', 'n/a')}`",
        f"- pilot_eligible: `{summary.get('pilot_eligible', False)}`",
        f"- full_split_run: `{summary.get('full_split_run', False)}`",
        f"- num_cases: `{summary.get('num_cases', 'n/a')}`",
        f"- full_case_count: `{summary.get('full_case_count', 'n/a')}`",
        f"- llm_provider: `{summary.get('llm_provider')}`",
        f"- llm_model_name: `{summary.get('llm_model_name')}`",
        f"- rewrite_llm_provider: `{summary.get('rewrite_llm_provider')}`",
        f"- uses_real_llm: `{summary.get('uses_real_llm', False)}`",
        f"- uses_real_embedding: `{summary.get('uses_real_embedding', False)}`",
        f"- uses_real_reranker: `{summary.get('uses_real_reranker', False)}`",
        f"- reranker_unavailable: `{summary.get('reranker_unavailable', False)}`",
        f"- llm_call_count: `{summary.get('llm_call_count')}` "
        f"(answer: `{summary.get('answer_llm_call_count')}`, "
        f"rewrite: `{summary.get('rewrite_llm_call_count')}`)",
        f"- llm_usage_total_tokens: `{summary.get('llm_usage_total_tokens')}` "
        f"(reported: `{summary.get('llm_usage_reported', False)}`)",
        f"- real_llm_invoked: `{summary.get('real_llm_invoked', False)}`",
        *(
            [f"- real_run_call_warning: {summary['real_run_call_warning']}"]
            if summary.get("real_run_call_warning")
            else []
        ),
        f"- expected_rewrite_used: `{summary.get('expected_rewrite_used', False)}`",
        f"- mock_used: `{summary.get('mock_used', False)}`",
        f"- toy_retrieval: `{summary.get('toy_retrieval', False)}`",
        f"- unavailable_systems: `{summary.get('unavailable_systems', {})}`",
        *(
            [f"- pilot_run_note: {summary['pilot_run_note']}"]
            if summary.get("pilot_run_note")
            else []
        ),
        "",
        _headline_banner(summary),
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
        "## Real-Run Interpretation (Week 6)",
        "",
        "- grounded_correctness is the headline metric (raw_correct AND citation_valid "
        "AND core-claim support). raw_correctness is reported only for contamination / "
        "parametric-leakage analysis and must not be quoted as a headline.",
        "- direct_llm (no retrieved context, no citations) is a parametric baseline; the "
        "gap between direct_llm raw_correctness and a grounded system's grounded_correctness "
        "is the parametric_leakage_gap, not a quality score.",
        "- final_agentic only triggers an LLM query rewrite when first-pass evidence is "
        "insufficient and the case is not blocked by permission/conflict/deprecation. When "
        "agentic shows no second_pass_improvement, that 0 is reported honestly.",
        "- Small samples are pilot runs; see pilot_run_note above. They are not final "
        "full-corpus numbers and must not be presented as such.",
        "- Pilot runs can be marked pilot_eligible=true as evidence that the real pipeline "
        "is wired, but they always have headline_eligible=false and headline_scope=pilot.",
        "- Observed pilot behavior: the trust gates refuse a sizable share of queries "
        "because real retrieval surfaces restricted, deprecated, or conflicting neighbors "
        "that trip the permission/deprecation/conflict gates. Correct refusals count as "
        "grounded; incorrect over-refusals depress grounded_correctness and are a "
        "gate-precision follow-up, not an eval-wiring defect (the live /chat pipeline "
        "refuses the same queries).",
        "- external and obfuscated real pilots run against the rebuilt public-corpus index "
        "(public chunks in Qdrant). The sample/fixture corpus is a separate index state; "
        "switching back requires rebuilding the sample index (see operational restore note).",
        "- LLM call accounting (llm_call_count / answer_llm_call_count / "
        "rewrite_llm_call_count and token usage) is recorded in summary.json so a real run "
        "that made zero API calls is never presented as a completed real LLM eval.",
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


def _headline_banner(summary: dict[str, Any]) -> str:
    if summary.get("headline_eligible"):
        return (
            "> Headline-eligible real run. grounded_correctness is the headline metric; "
            "raw_correctness is reported only for contamination / parametric-leakage "
            "analysis. Small samples are pilot runs, not final full runs."
        )
    if summary.get("headline_scope") == "pilot":
        return (
            "> Pilot run. These metrics demonstrate pipeline validity and cost behavior, "
            "but are not final headline metrics."
        )
    return (
        "> NOT headline-eligible. The metrics below are smoke/diagnostic only and must "
        "not be cited as headline results."
    )


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
    reason_counts = Counter(failure.get("reason", "unknown") for failure in failures)
    lines = [
        "# Failure Analysis",
        "",
        "This draft is generated from the latest local eval run.",
        "",
        f"Failure rows: {len(failures)}",
        "",
        "## Failure Reason Distribution",
        "",
        "```json",
        json.dumps(dict(sorted(reason_counts.items())), ensure_ascii=False, indent=2),
        "```",
        "",
        "> Week 6 note: `grounded_correctness_false` failures in the pilot are dominated by "
        "trust-gate refusals (permission/conflict) on answerable queries, because real "
        "retrieval surfaces versioned and restricted neighbors. This is a gate-precision "
        "follow-up; the eval honestly records the refusals rather than masking them.",
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
        "Week 6: in real runs this sample is populated from real LLM answers bound to "
        "real retrieved chunks. Refused cases contribute no citations by design.",
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
