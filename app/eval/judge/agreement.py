from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.eval.judge.base import BaseJudge, JudgeVerdict

SUPPORTED = "supported"
NOT_SUPPORTED = "not_supported"


@dataclass(frozen=True)
class AuditExample:
    audit_id: str
    case_id: str
    eval_split: str
    claim_text: str
    cited_texts: list[str]
    label: str
    wrong_side_citation: bool
    synthetic: bool = False


@dataclass(frozen=True)
class CandidateRun:
    candidate_id: str
    verdicts: list[dict[str, Any]]


def run_agreement(
    *,
    judges: dict[str, BaseJudge],
    anchor_path: Path,
    gpt_reference_path: Path | None,
    probe_path: Path,
    output_dir: Path,
    settings: Settings,
    bootstrap_samples: int = 1000,
) -> dict[str, Any]:
    anchors = load_examples(anchor_path)
    probes = load_examples(probe_path)
    gpt_reference = load_gpt_reference(gpt_reference_path) if gpt_reference_path else {}

    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_runs: dict[str, CandidateRun] = {}
    for candidate_id, judge in judges.items():
        verdict_rows = [
            _judge_example(candidate_id=candidate_id, judge=judge, example=example)
            for example in anchors
        ]
        _write_jsonl(output_dir / f"{candidate_id}_verdicts.jsonl", verdict_rows)
        candidate_runs[candidate_id] = CandidateRun(candidate_id, verdict_rows)

    probe_rows: list[dict[str, Any]] = []
    for candidate_id, judge in judges.items():
        for example in probes:
            probe_rows.append(
                _judge_example(candidate_id=candidate_id, judge=judge, example=example)
            )
    _write_jsonl(output_dir / "probe_verdicts.jsonl", probe_rows)

    summary = build_summary(
        anchors=anchors,
        probes=probes,
        candidate_runs=candidate_runs,
        probe_rows=probe_rows,
        gpt_reference=gpt_reference,
        settings=settings,
        bootstrap_samples=bootstrap_samples,
    )
    (output_dir / "agreement_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def load_examples(path: Path) -> list[AuditExample]:
    examples: list[AuditExample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        snapshots = record.get("cited_text_snapshot") or {}
        if isinstance(snapshots, dict):
            cited_texts = [str(text) for text in snapshots.values()]
        else:
            cited_texts = [str(item) for item in snapshots]
        examples.append(
            AuditExample(
                audit_id=str(record["audit_id"]),
                case_id=str(record.get("case_id", record["audit_id"])),
                eval_split=str(record.get("eval_split", "unknown")),
                claim_text=str(record["claim_text"]),
                cited_texts=cited_texts,
                label=str(record["label"]).lower(),
                wrong_side_citation=bool(record.get("wrong_side_citation", False)),
                synthetic=bool(record.get("synthetic", False)),
            )
        )
    return examples


def load_gpt_reference(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    reference: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        reference[str(record["audit_id"])] = record
    return reference


def build_summary(
    *,
    anchors: list[AuditExample],
    probes: list[AuditExample],
    candidate_runs: dict[str, CandidateRun],
    probe_rows: list[dict[str, Any]],
    gpt_reference: dict[str, dict[str, Any]],
    settings: Settings,
    bootstrap_samples: int = 1000,
) -> dict[str, Any]:
    metrics = {
        candidate_id: agreement_metrics(
            anchors,
            run.verdicts,
            bootstrap_samples=bootstrap_samples,
        )
        for candidate_id, run in candidate_runs.items()
    }
    probe_metrics = probe_floor_metrics(probes, probe_rows)
    selection = select_candidate(metrics, probe_metrics)
    return {
        "run_id": "judge-agreement-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "headline_eligible": False,
        "headline_scope": "none",
        "judge_based": True,
        "judge_based_note": (
            "LLM judge outputs are validation artifacts, not human citation accuracy."
        ),
        "limitations": {
            "anchor_n": len(anchors),
            "anchor_label_counts": dict(Counter(example.label for example in anchors)),
            "no_unsupported_real_anchors": True,
            "no_wrong_side_real_anchors": True,
            "wrong_side_validation": "probe_only_until_hard_negative_rewrite_anchors",
        },
        "judge_model": {
            "provider": settings.judge_llm_provider,
            "model_name": settings.judge_llm_model_name,
            "base_url_host": _host(settings.judge_llm_base_url),
            "temperature": settings.judge_llm_temperature,
            "max_output_tokens": settings.judge_llm_max_output_tokens,
        },
        "candidate_implementation": {
            "ragas": "RAGAS-style faithfulness prompt adapter; no RAGAS package dependency.",
            "deepeval": (
                "DeepEval-style faithfulness/G-Eval prompt adapter; "
                "no DeepEval package dependency."
            ),
            "custom": "Project custom 3-way citation-support prompt from JUDGE_PROTOCOL.",
        },
        "candidates": metrics,
        "probe": probe_metrics,
        "candidate_vs_candidate": candidate_vs_candidate(candidate_runs),
        "candidate_vs_gpt_reference": candidate_vs_gpt(anchors, candidate_runs, gpt_reference),
        "selection": selection,
    }


def agreement_metrics(
    anchors: list[AuditExample],
    verdict_rows: list[dict[str, Any]],
    *,
    bootstrap_samples: int = 1000,
) -> dict[str, Any]:
    by_id = {str(row["audit_id"]): row for row in verdict_rows}
    pairs = [(example, by_id[example.audit_id]) for example in anchors]
    binary_matches = [
        binary_label(row["label"]) == binary_label(example.label) for example, row in pairs
    ]
    exact_matches = [row["label"] == example.label for example, row in pairs]
    per_split: dict[str, dict[str, Any]] = {}
    for split, split_pairs in _group_pairs_by_split(pairs).items():
        split_binary = [
            binary_label(row["label"]) == binary_label(example.label)
            for example, row in split_pairs
        ]
        per_split[split] = {
            "n": len(split_pairs),
            "binary_correct": sum(split_binary),
            "binary_agreement": _mean(split_binary) if len(split_pairs) >= 5 else None,
            "note": "n<5; report counts only" if len(split_pairs) < 5 else "",
        }
    return {
        "n": len(pairs),
        "binary_agreement": _mean(binary_matches),
        "exact_agreement": _mean(exact_matches),
        "cohen_kappa_binary": cohen_kappa_binary(
            [binary_label(example.label) for example, _row in pairs],
            [binary_label(row["label"]) for _example, row in pairs],
        ),
        "bootstrap_ci_binary_agreement_95": bootstrap_ci(
            binary_matches,
            samples=bootstrap_samples,
        ),
        "per_stratum": per_split,
        "label_counts": dict(Counter(str(row["label"]) for _example, row in pairs)),
        "wrong_side_predicted_count": sum(bool(row["wrong_side"]) for _example, row in pairs),
        "warnings_count": sum(len(row.get("warnings", [])) for _example, row in pairs),
    }


def probe_floor_metrics(
    probes: list[AuditExample],
    probe_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in probe_rows:
        by_candidate[str(row["candidate_id"])].append(row)
    expected_by_id = {probe.audit_id: probe for probe in probes}
    result: dict[str, Any] = {}
    for candidate_id, rows in by_candidate.items():
        correct = 0
        details = []
        for row in rows:
            expected = expected_by_id[str(row["audit_id"])]
            label_ok = binary_label(row["label"]) == binary_label(expected.label)
            wrong_side_ok = (
                bool(row["wrong_side"]) is True
                if expected.wrong_side_citation
                else True
            )
            row_ok = label_ok and wrong_side_ok
            correct += int(row_ok)
            details.append(
                {
                    "audit_id": row["audit_id"],
                    "expected_label": expected.label,
                    "predicted_label": row["label"],
                    "expected_wrong_side": expected.wrong_side_citation,
                    "predicted_wrong_side": row["wrong_side"],
                    "correct": row_ok,
                }
            )
        result[candidate_id] = {
            "n": len(rows),
            "correct": correct,
            "probe_floor": correct / len(rows) if rows else 0.0,
            "passes_probe_gate": correct >= 4,
            "details": details,
        }
    return result


def select_candidate(metrics: dict[str, Any], probe_metrics: dict[str, Any]) -> dict[str, Any]:
    eligible = []
    for candidate_id, candidate_metrics in metrics.items():
        passes_g2 = candidate_metrics["binary_agreement"] >= 0.80
        passes_probe = bool(probe_metrics.get(candidate_id, {}).get("passes_probe_gate"))
        if passes_g2 and passes_probe:
            eligible.append((candidate_id, candidate_metrics["binary_agreement"]))
    if not eligible:
        return {
            "deploy_judge": False,
            "selected_candidate": None,
            "reason": "No candidate passed both G2 binary_agreement>=0.80 and probe_floor>=4/5.",
        }
    best_score = max(score for _candidate_id, score in eligible)
    tied = sorted(candidate_id for candidate_id, score in eligible if score == best_score)
    selected = "custom" if "custom" in tied else tied[0]
    return {
        "deploy_judge": True,
        "selected_candidate": selected,
        "reason": "Selected highest binary agreement; ties prefer custom J-C.",
    }


def candidate_vs_candidate(candidate_runs: dict[str, CandidateRun]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    ids = sorted(candidate_runs)
    for left_index, left_id in enumerate(ids):
        left = {row["audit_id"]: row for row in candidate_runs[left_id].verdicts}
        for right_id in ids[left_index + 1 :]:
            right = {row["audit_id"]: row for row in candidate_runs[right_id].verdicts}
            shared_ids = sorted(set(left) & set(right))
            matches = [
                binary_label(left[audit_id]["label"]) == binary_label(right[audit_id]["label"])
                for audit_id in shared_ids
            ]
            result[f"{left_id}_vs_{right_id}"] = {
                "n": len(shared_ids),
                "binary_agreement": _mean(matches),
            }
    return result


def candidate_vs_gpt(
    anchors: list[AuditExample],
    candidate_runs: dict[str, CandidateRun],
    gpt_reference: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    anchor_ids = {anchor.audit_id for anchor in anchors}
    for candidate_id, run in candidate_runs.items():
        shared = [
            row
            for row in run.verdicts
            if row["audit_id"] in gpt_reference and row["audit_id"] in anchor_ids
        ]
        matches = [
            binary_label(row["label"])
            == binary_label(str(gpt_reference[row["audit_id"]].get("label", "")))
            for row in shared
        ]
        result[candidate_id] = {
            "n": len(shared),
            "binary_agreement": _mean(matches),
        }
    return result


def cohen_kappa_binary(human: list[str], judge: list[str]) -> float:
    if not human or len(human) != len(judge):
        return 0.0
    observed = sum(h == j for h, j in zip(human, judge, strict=True)) / len(human)
    human_counts = Counter(human)
    judge_counts = Counter(judge)
    expected = sum(
        (human_counts[label] / len(human)) * (judge_counts[label] / len(judge))
        for label in {SUPPORTED, NOT_SUPPORTED}
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def bootstrap_ci(
    matches: list[bool],
    *,
    samples: int = 1000,
    seed: int = 20260615,
) -> dict[str, float]:
    if not matches:
        return {"low": 0.0, "high": 0.0}
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        resampled = [matches[rng.randrange(len(matches))] for _item in matches]
        estimates.append(_mean(resampled))
    estimates.sort()
    low_index = int(0.025 * (samples - 1))
    high_index = int(0.975 * (samples - 1))
    return {"low": estimates[low_index], "high": estimates[high_index]}


def binary_label(label: str) -> str:
    return SUPPORTED if str(label).lower() == SUPPORTED else NOT_SUPPORTED


def _judge_example(
    *,
    candidate_id: str,
    judge: BaseJudge,
    example: AuditExample,
) -> dict[str, Any]:
    verdict = judge.judge(example.claim_text, example.cited_texts)
    return verdict_row(candidate_id=candidate_id, example=example, verdict=verdict)


def verdict_row(
    *,
    candidate_id: str,
    example: AuditExample,
    verdict: JudgeVerdict,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "audit_id": example.audit_id,
        "case_id": example.case_id,
        "eval_split": example.eval_split,
        "synthetic": example.synthetic,
        "label": verdict.label,
        "wrong_side": verdict.wrong_side,
        "rationale": verdict.rationale,
        "warnings": verdict.warnings,
        "judge_based": verdict.judge_based,
    }


def _group_pairs_by_split(
    pairs: list[tuple[AuditExample, dict[str, Any]]],
) -> dict[str, list[tuple[AuditExample, dict[str, Any]]]]:
    grouped: dict[str, list[tuple[AuditExample, dict[str, Any]]]] = defaultdict(list)
    for example, row in pairs:
        grouped[example.eval_split].append((example, row))
    return grouped


def _mean(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 0.0


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _host(base_url: str | None) -> str | None:
    if not base_url:
        return None
    without_scheme = base_url.split("://", 1)[-1]
    return without_scheme.split("/", 1)[0]
