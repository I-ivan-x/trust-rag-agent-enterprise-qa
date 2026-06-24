# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.actions import ActionProposal, materialize_proposal
from app.agent.diagnosis import ActionType, diagnose
from app.core.config import get_settings
from app.core.enums import EvalSplit
from app.eval.dataset import chunk_path_for_split, load_eval_cases, write_jsonl
from app.guards.evidence_gate import evidence_gate_config_from_settings
from app.index.build_index import INDEX_METADATA_PATH, read_index_metadata
from app.rerank.reranker import get_reranker
from app.schemas.retrieval import RetrievalOptions
from app.service.chat_service import _make_hybrid_retriever
from app.workflow.orchestrator import run_trust_gated_pass
from scripts.rebuild_indexes import rebuild_indexes

DEFAULT_SPLITS = (EvalSplit.obfuscated, EvalSplit.agent_residual)
DEFAULT_RUN_ID = "p3-09-diagnostic-precheck"
PRECHECK_OPTIONS = RetrievalOptions(
    top_k_dense=20,
    top_k_sparse=20,
    top_n_rerank=8,
    return_trace=True,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the P3-09 zero-token agent diagnostic precheck."
    )
    parser.add_argument(
        "--splits",
        default=",".join(split.value for split in DEFAULT_SPLITS),
        help="Comma-separated eval splits to precheck.",
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output-root", type=Path, default=Path("data/eval_runs"))
    parser.add_argument(
        "--doc-output",
        type=Path,
        default=Path("docs/P3_09_DIAGNOSTIC_PRECHECK.md"),
    )
    parser.add_argument(
        "--embedding-provider",
        choices=["mock", "sentence_transformer", "openai_compatible"],
        default=None,
        help="Embedding provider for per-split index rebuilds.",
    )
    parser.add_argument(
        "--no-rebuild-index",
        action="store_true",
        help="Use the current index; valid only when it matches the selected split.",
    )
    parser.add_argument(
        "--allow-vector-unavailable",
        action="store_true",
        help=(
            "Record keyword-only fallback instead of failing when vector retrieval "
            "is unavailable."
        ),
    )
    parser.add_argument(
        "--allow-reranker-unavailable",
        action="store_true",
        help=(
            "Record identity rerank fallback instead of failing when the configured "
            "reranker is unavailable."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    splits = _parse_splits(args.splits)
    run_dir = args.output_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    split_summaries: list[dict[str, Any]] = []
    for split in splits:
        split_summary, split_records = _run_split(
            split,
            rebuild_index=not args.no_rebuild_index,
            embedding_provider=args.embedding_provider,
            allow_vector_unavailable=args.allow_vector_unavailable,
            allow_reranker_unavailable=args.allow_reranker_unavailable,
        )
        split_summaries.append(split_summary)
        records.extend(split_records)

    summary = _build_summary(args.run_id, split_summaries, records)
    json_payload = {"summary": summary, "cases": records}
    (run_dir / "diagnostic_precheck.json").write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_jsonl(run_dir / "diagnostic_precheck_cases.jsonl", records)
    args.doc_output.write_text(_markdown(summary, records), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def _run_split(
    split: EvalSplit,
    *,
    rebuild_index: bool,
    embedding_provider: str | None,
    allow_vector_unavailable: bool,
    allow_reranker_unavailable: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    chunks_path = chunk_path_for_split(split)
    index_summary: dict[str, Any] | None = None
    if rebuild_index:
        index_summary = rebuild_indexes(
            chunks_path=chunks_path,
            embedding_provider=embedding_provider,
            include_agent_residual=split is EvalSplit.agent_residual,
        )
        if not allow_vector_unavailable and not index_summary.get("vector_index_built"):
            raise RuntimeError(
                "Vector index was not built for "
                f"{split.value}; rerun with Qdrant available or pass "
                "--allow-vector-unavailable to record fallback explicitly."
            )
    else:
        _require_matching_index(chunks_path)

    retriever = _make_hybrid_retriever()
    vector_available = getattr(retriever, "vector_retriever", None) is not None
    if not allow_vector_unavailable and not vector_available:
        raise RuntimeError(
            f"Vector retriever unavailable for {split.value}; this would be keyword-only."
        )

    reranker_unavailable = False
    try:
        reranker = get_reranker(get_settings().reranker_provider)
    except Exception as exc:
        if not allow_reranker_unavailable:
            raise RuntimeError(
                f"Reranker unavailable for {split.value}: {type(exc).__name__}: {exc}"
            ) from exc
        from app.eval.real_pipeline import _IdentityReranker

        reranker = _IdentityReranker()
        reranker_unavailable = True

    cases = load_eval_cases(split)
    records: list[dict[str, Any]] = []
    evidence_gate_config = evidence_gate_config_from_settings(get_settings())
    for case in cases:
        first_pass = run_trust_gated_pass(
            query=case.query,
            retrieval_options=PRECHECK_OPTIONS,
            retriever=retriever,
            reranker=reranker,
            user_role=case.user_role,
            user_department=case.user_department,
            user_clearance=case.user_clearance.value,
            evidence_gate_config=evidence_gate_config,
        )
        report = diagnose(first_pass)
        action_b_probe = _action_b_probe(
            case=case,
            first_pass=first_pass,
            first_report=report,
            retriever=retriever,
            reranker=reranker,
            evidence_gate_config=evidence_gate_config,
        )
        records.append(
            _case_record(
                case=case,
                split=split,
                report=report,
                first_pass=first_pass,
                action_b_probe=action_b_probe,
                vector_available=vector_available,
                reranker_unavailable=reranker_unavailable,
            )
        )

    split_summary = {
        "split": split.value,
        "case_count": len(cases),
        "chunks_path": chunks_path.as_posix(),
        "index_summary": index_summary,
        "index_metadata": read_index_metadata(INDEX_METADATA_PATH),
        "vector_available": vector_available,
        "reranker_unavailable": reranker_unavailable,
    }
    return split_summary, records


def _action_b_probe(
    *,
    case,
    first_pass,
    first_report,
    retriever,
    reranker,
    evidence_gate_config,
) -> dict[str, Any]:
    policy_neighbor_count = (
        first_report.deprecated_neighbor_count + first_report.restricted_neighbor_count
    )
    legal_actions = [action.value for action in first_report.legal_actions]
    probe: dict[str, Any] = {
        "policy_neighbor_count": policy_neighbor_count,
        "policy_neighbor_surface": policy_neighbor_count >= 2,
        "legal_triggered": ActionType.filtered_retrieval.value in legal_actions,
        "filtered_retrieval_attempted": False,
        "filters": None,
        "filtered_evidence_decision": None,
        "filtered_evidence_reason": None,
        "filtered_failure_type": None,
        "filtered_gold_doc_hit_at_5": None,
        "filtered_gold_chunk_hit_at_5": None,
        "recoverable": False,
        "gold_doc_recoverable": False,
    }
    if not probe["policy_neighbor_surface"]:
        return probe

    proposal = materialize_proposal(
        ActionProposal(action=ActionType.filtered_retrieval),
        query=first_pass.query,
        pass_result=first_pass,
    )
    filters = proposal.args.get("filters") or {}
    filtered_pass = run_trust_gated_pass(
        query=first_pass.query,
        retrieval_options=PRECHECK_OPTIONS,
        retriever=retriever,
        reranker=reranker,
        user_role=case.user_role,
        user_department=case.user_department,
        user_clearance=case.user_clearance.value,
        evidence_gate_config=evidence_gate_config,
        filters=filters,
    )
    filtered_report = diagnose(filtered_pass)
    filtered_hits = _gold_hits(case, filtered_pass.reranked_chunks)
    first_hits = _gold_hits(case, first_pass.reranked_chunks)
    first_insufficient = first_report.evidence_decision == "insufficient"
    filtered_sufficient = filtered_report.evidence_decision == "sufficient"
    probe.update(
        {
            "filtered_retrieval_attempted": True,
            "filters": filters,
            "filtered_evidence_decision": filtered_report.evidence_decision,
            "filtered_evidence_reason": filtered_pass.evidence_decision.reason,
            "filtered_failure_type": filtered_report.failure_type.value,
            "filtered_gold_doc_hit_at_5": filtered_hits["gold_doc_hit_at_5"],
            "filtered_gold_chunk_hit_at_5": filtered_hits["gold_chunk_hit_at_5"],
            "recoverable": bool(first_insufficient and filtered_sufficient),
            "gold_doc_recoverable": bool(
                first_insufficient
                and not first_hits["gold_doc_hit_at_5"]
                and filtered_hits["gold_doc_hit_at_5"]
            ),
        }
    )
    return probe


def _case_record(
    *,
    case,
    split,
    report,
    first_pass,
    action_b_probe,
    vector_available,
    reranker_unavailable,
):
    legal_actions = [action.value for action in report.legal_actions]
    retrieved_doc_ids = [item.chunk.doc_id for item in first_pass.reranked_chunks[:10]]
    retrieved_chunk_ids = [item.chunk.chunk_id for item in first_pass.reranked_chunks[:10]]
    hits = _gold_hits(case, first_pass.reranked_chunks)
    action_d = {
        "conflict_surface": bool(report.conflict_group_ids),
        "legal_triggered": ActionType.present_conflict_set.value in legal_actions,
        "conflict_group_ids": report.conflict_group_ids,
    }
    return {
        "case_id": case.case_id,
        "split": split.value,
        "query": case.query,
        "evidence_decision": report.evidence_decision,
        "evidence_reason": first_pass.evidence_decision.reason,
        "failure_type": report.failure_type.value,
        "legal_actions": legal_actions,
        "weak_recall_triggered": ActionType.rewrite_query.value in legal_actions,
        "action_a": {
            "legal_triggered": ActionType.rewrite_query.value in legal_actions,
        },
        "action_b": action_b_probe,
        "action_d": action_d,
        "signals": {
            "permission_blocked_count": report.permission_blocked_count,
            "deprecated_neighbor_count": report.deprecated_neighbor_count,
            "restricted_neighbor_count": report.restricted_neighbor_count,
            "conflict_group_ids": report.conflict_group_ids,
            "clean_active_count": report.clean_active_count,
            "top_rerank_score": report.top_rerank_score,
            "support_chunk_count": report.support_chunk_count,
            "entity_miss": report.entity_miss,
        },
        "gold_doc_hit_at_5": hits["gold_doc_hit_at_5"],
        "gold_chunk_hit_at_5": hits["gold_chunk_hit_at_5"],
        "retrieved_doc_ids": retrieved_doc_ids,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "warnings": first_pass.warnings,
        "vector_available": vector_available,
        "reranker_unavailable": reranker_unavailable,
    }


def _gold_hits(case, reranked_chunks) -> dict[str, bool]:
    retrieved_doc_ids = [item.chunk.doc_id for item in reranked_chunks[:5]]
    retrieved_chunk_ids = [item.chunk.chunk_id for item in reranked_chunks[:5]]
    return {
        "gold_doc_hit_at_5": bool(set(case.gold_doc_ids) & set(retrieved_doc_ids)),
        "gold_chunk_hit_at_5": bool(set(case.gold_chunk_ids) & set(retrieved_chunk_ids)),
    }


def _build_summary(
    run_id: str,
    split_summaries: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    failure_distribution = Counter(record["failure_type"] for record in records)
    legal_distribution = Counter(_legal_key(record["legal_actions"]) for record in records)
    by_split = {}
    for split in sorted({record["split"] for record in records}):
        split_records = [record for record in records if record["split"] == split]
        by_split[split] = {
            "case_count": len(split_records),
            "failure_distribution": dict(
                sorted(Counter(record["failure_type"] for record in split_records).items())
            ),
            "legal_action_distribution": dict(
                sorted(
                    Counter(_legal_key(record["legal_actions"]) for record in split_records).items()
                )
            ),
            "weak_recall_trigger_count": sum(
                1 for record in split_records if record["weak_recall_triggered"]
            ),
            "action_a_trigger_count": _count(
                split_records,
                lambda record: record["action_a"]["legal_triggered"],
            ),
            "action_b_policy_neighbor_count": _count(
                split_records,
                lambda record: record["action_b"]["policy_neighbor_surface"],
            ),
            "action_b_legal_count": _count(
                split_records,
                lambda record: record["action_b"]["legal_triggered"],
            ),
            "action_b_recoverable_count": _count(
                split_records,
                lambda record: record["action_b"]["recoverable"],
            ),
            "action_b_gold_doc_recoverable_count": _count(
                split_records,
                lambda record: record["action_b"]["gold_doc_recoverable"],
            ),
            "action_d_conflict_surface_count": _count(
                split_records,
                lambda record: record["action_d"]["conflict_surface"],
            ),
            "action_d_legal_count": _count(
                split_records,
                lambda record: record["action_d"]["legal_triggered"],
            ),
        }
    action_a_count = _count(records, lambda record: record["action_a"]["legal_triggered"])
    action_b_policy_count = _count(
        records,
        lambda record: record["action_b"]["policy_neighbor_surface"],
    )
    action_b_legal_count = _count(
        records,
        lambda record: record["action_b"]["legal_triggered"],
    )
    action_b_recoverable_count = _count(
        records,
        lambda record: record["action_b"]["recoverable"],
    )
    action_b_gold_recoverable_count = _count(
        records,
        lambda record: record["action_b"]["gold_doc_recoverable"],
    )
    action_d_surface_count = _count(
        records,
        lambda record: record["action_d"]["conflict_surface"],
    )
    action_d_legal_count = _count(
        records,
        lambda record: record["action_d"]["legal_triggered"],
    )
    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "zero_token_diagnostic_precheck",
        "llm_call_count": 0,
        "llm_usage_total_tokens": 0,
        "case_count": len(records),
        "splits": [summary["split"] for summary in split_summaries],
        "failure_distribution": dict(sorted(failure_distribution.items())),
        "legal_action_distribution": dict(sorted(legal_distribution.items())),
        "weak_recall_trigger_count": sum(
            1 for record in records if record["weak_recall_triggered"]
        ),
        "residual_action_profile": {
            "action_a_rewrite_query": {
                "legal_trigger_count": action_a_count,
            },
            "action_b_filtered_retrieval": {
                "policy_neighbor_surface_count": action_b_policy_count,
                "legal_trigger_count": action_b_legal_count,
                "recoverable_count": action_b_recoverable_count,
                "gold_doc_recoverable_count": action_b_gold_recoverable_count,
            },
            "action_d_present_conflict_set": {
                "conflict_surface_count": action_d_surface_count,
                "legal_trigger_count": action_d_legal_count,
            },
        },
        "weak_recall_minimum_for_rewrite_bed": 8,
        "weak_recall_bed_sufficient": action_a_count >= 8,
        "by_split": by_split,
        "split_index_summaries": split_summaries,
        "notes": {
            "record_not_halt": (
                "P3-09 revised records the real diagnostic surface; it no longer "
                "halts on sparse a/b co-occurrence."
            ),
            "action_d_boundary": (
                "present_conflict_set overlaps Q1 report_conflict and is expected "
                "only for conflict-detected plus evidence-insufficient corner cases."
            ),
        },
    }


def _count(records: list[dict[str, Any]], predicate) -> int:
    return sum(1 for record in records if predicate(record))


def _markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    profile = summary["residual_action_profile"]
    action_b = profile["action_b_filtered_retrieval"]
    action_d = profile["action_d_present_conflict_set"]
    lines = [
        "# P3-09 Diagnostic Precheck",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- created_at: `{summary['created_at']}`",
        "- mode: zero-token diagnostic precheck",
        "- llm_call_count: 0",
        "- llm_usage_total_tokens: 0",
        f"- case_count: {summary['case_count']}",
        f"- weak_recall/action-a trigger_count: {summary['weak_recall_trigger_count']}",
        (
            "- action-b policy-neighbor surface_count: "
            f"{action_b['policy_neighbor_surface_count']}"
        ),
        f"- action-b legal trigger_count: {action_b['legal_trigger_count']}",
        f"- action-b filter-recoverable count: {action_b['recoverable_count']}",
        (
            "- action-b gold-doc-recoverable count: "
            f"{action_b['gold_doc_recoverable_count']}"
        ),
        f"- action-d active-conflict surface_count: {action_d['conflict_surface_count']}",
        f"- action-d legal trigger_count: {action_d['legal_trigger_count']}",
        f"- weak_recall bed sufficient (>=8): {summary['weak_recall_bed_sufficient']}",
        "",
        "## Diagnostic Distribution",
        "",
        "| failure_type | count |",
        "| --- | ---: |",
    ]
    for failure_type, count in summary["failure_distribution"].items():
        lines.append(f"| `{failure_type}` | {count} |")
    lines.extend(
        [
            "",
            "## Legal Action Distribution",
            "",
            "| legal_actions | count |",
            "| --- | ---: |",
        ]
    )
    for legal_actions, count in summary["legal_action_distribution"].items():
        lines.append(f"| `{legal_actions}` | {count} |")
    lines.extend(
        [
            "",
            "## By Split",
            "",
            (
                "| split | cases | a triggers | b policy | b legal | b recoverable | "
                "d surface | d legal | failure_distribution |"
            ),
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for split, split_summary in summary["by_split"].items():
        lines.append(
            "| "
            f"`{split}` | "
            f"{split_summary['case_count']} | "
            f"{split_summary['weak_recall_trigger_count']} | "
            f"{split_summary['action_b_policy_neighbor_count']} | "
            f"{split_summary['action_b_legal_count']} | "
            f"{split_summary['action_b_recoverable_count']} | "
            f"{split_summary['action_d_conflict_surface_count']} | "
            f"{split_summary['action_d_legal_count']} | "
            f"`{json.dumps(split_summary['failure_distribution'], sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            (
                "- RECORD not HALT: the precheck archives real diagnostic scarcity "
                "instead of requiring >=6 a/b co-occurrence."
            ),
            (
                "- Action d is retained for attribution, but overlaps Q1 "
                "`report_conflict`; it is not a primary P3-09 ability readout."
            ),
            "",
            "## Per Case",
            "",
            (
                "| split | case_id | failure_type | legal_actions | clean | policy | "
                "entity_miss | a | b_legal | b_save | d_surface | d_legal | gold_doc@5 |"
            ),
            "| --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in records:
        signals = record["signals"]
        action_b_record = record["action_b"]
        action_d_record = record["action_d"]
        lines.append(
            "| "
            f"`{record['split']}` | "
            f"`{record['case_id']}` | "
            f"`{record['failure_type']}` | "
            f"`{_legal_key(record['legal_actions'])}` | "
            f"{signals['clean_active_count']} | "
            f"{action_b_record['policy_neighbor_count']} | "
            f"{signals['entity_miss']} | "
            f"{record['action_a']['legal_triggered']} | "
            f"{action_b_record['legal_triggered']} | "
            f"{action_b_record['recoverable']} | "
            f"{action_d_record['conflict_surface']} | "
            f"{action_d_record['legal_triggered']} | "
            f"{record['gold_doc_hit_at_5']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _require_matching_index(chunks_path: Path) -> None:
    metadata = read_index_metadata(INDEX_METADATA_PATH)
    if metadata is None:
        raise RuntimeError(f"Index metadata missing at {INDEX_METADATA_PATH}")
    indexed_path = str(metadata.get("chunks_path") or "").replace("\\", "/")
    expected_path = chunks_path.as_posix()
    if indexed_path != expected_path:
        raise RuntimeError(
            "Current index does not match selected split: "
            f"index_chunks_path={indexed_path}, expected={expected_path}"
        )


def _parse_splits(value: str) -> list[EvalSplit]:
    splits = [EvalSplit(item.strip()) for item in value.split(",") if item.strip()]
    if not splits:
        raise ValueError("At least one split is required.")
    return splits


def _legal_key(actions: list[str]) -> str:
    return ",".join(actions) if actions else "none"


if __name__ == "__main__":
    main()
