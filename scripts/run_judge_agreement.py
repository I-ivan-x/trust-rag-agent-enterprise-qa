# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.eval.judge.agreement import run_agreement
from app.eval.judge.base import BaseLLM
from app.eval.judge.client import get_judge_llm_client
from app.eval.judge.custom_judge import CustomCitationJudge
from app.eval.judge.deepeval_judge import DeepEvalFaithfulnessJudge
from app.eval.judge.ragas_judge import RagasFaithfulnessJudge


class MockJudgeLLM:
    """Deterministic local smoke client; never use for judge selection."""

    def generate(self, prompt: str) -> str:
        lower = prompt.lower()
        wrong_side = "path parameters" in lower and "query parameters" in lower
        unsupported = (
            "unrelated evidence" in lower
            or ("cors" in lower and "file" in lower and "claim" in lower)
            or ("oauth2" in lower and "partial updates" in lower)
        )
        if '"faithful"' in prompt:
            return json.dumps(
                {
                    "faithful": not unsupported and not wrong_side,
                    "rationale": "mock smoke verdict",
                }
            )
        if '"pass"' in prompt:
            return json.dumps(
                {"pass": not unsupported and not wrong_side, "rationale": "mock smoke verdict"}
            )
        label = "unsupported" if unsupported or wrong_side else "supported"
        if "now let's go back a bit" in lower or "the same way you use `body`" in lower:
            label = "weak"
        return json.dumps(
            {
                "label": label,
                "wrong_side_citation": wrong_side,
                "rationale": "mock smoke verdict",
            }
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 2 judge agreement harness.")
    parser.add_argument(
        "--anchors",
        type=Path,
        default=Path("data/citation_audit/manual_audit_v1_labels.jsonl"),
    )
    parser.add_argument(
        "--gpt-reference",
        type=Path,
        default=Path("data/citation_audit/judge_pass_v1_gpt_labels.jsonl"),
    )
    parser.add_argument(
        "--probes",
        type=Path,
        default=Path("data/citation_audit/discriminative_probes.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/eval_runs/judge-agreement-v1"),
    )
    parser.add_argument("--mock", action="store_true", help="Use deterministic smoke LLM.")
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--write-report", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    llm_client: BaseLLM = MockJudgeLLM() if args.mock else get_judge_llm_client(settings)
    judges = {
        "ragas": RagasFaithfulnessJudge(llm_client),
        "deepeval": DeepEvalFaithfulnessJudge(llm_client),
        "custom": CustomCitationJudge(llm_client),
    }
    summary = run_agreement(
        judges=judges,
        anchor_path=args.anchors,
        gpt_reference_path=args.gpt_reference,
        probe_path=args.probes,
        output_dir=args.output_dir,
        settings=settings,
        bootstrap_samples=args.bootstrap_samples,
    )
    if args.write_report:
        write_report(summary, Path("docs/JUDGE_AGREEMENT_REPORT.md"))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def write_report(summary: dict, path: Path) -> None:
    candidates = summary["candidates"]
    probe = summary["probe"]
    rows = []
    for candidate_id in ["ragas", "deepeval", "custom"]:
        candidate = candidates[candidate_id]
        probe_metrics = probe[candidate_id]
        deployable = (
            candidate["binary_agreement"] >= 0.80
            and probe_metrics["passes_probe_gate"]
        )
        rows.append(
            "| {candidate} | {binary:.4f} | {exact:.4f} | {kappa:.4f} | "
            "{probe_correct}/{probe_n} | {deployable} |".format(
                candidate=f"`{candidate_id}`",
                binary=candidate["binary_agreement"],
                exact=candidate["exact_agreement"],
                kappa=candidate["cohen_kappa_binary"],
                probe_correct=probe_metrics["correct"],
                probe_n=probe_metrics["n"],
                deployable="yes" if deployable else "no",
            )
        )
    path.write_text(
        "\n".join(
            [
                "# Judge Agreement Report",
                "",
                f"Run: `{summary['run_id']}`, generated {summary['generated_at']} with "
                f"`JUDGE_LLM_PROVIDER={summary['judge_model']['provider']}`, "
                f"`JUDGE_LLM_MODEL_NAME={summary['judge_model']['model_name']}`, "
                f"`temperature={summary['judge_model']['temperature']}`.",
                "",
                "## Scope",
                "",
                "- `judge_based=true`; this is not headline evaluation and must not be "
                "reported as human citation accuracy.",
                "- Real anchor set: n=15, with 11 `supported` and 4 `weak` labels.",
                "- The anchor set has 0 real `unsupported` and 0 real `wrong_side` "
                "labels, so unsupported/wrong-side detection is probe-only until "
                "rewritten hard-negative anchors land.",
                "",
                "## Result",
                "",
                "No candidate is deployable for downstream judge-based metrics."
                if not summary["selection"]["deploy_judge"]
                else "A candidate passed the configured gates.",
                "",
                "| candidate | binary_agreement | exact_agreement | kappa_binary | "
                "probe_floor | deployable |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
                *rows,
                "",
                "Framework candidates are implemented as prompt adapters over the same "
                "secondary-family judge model; they do not add RAGAS/DeepEval as hard "
                "runtime dependencies.",
                "",
                "## Selection",
                "",
                f"- deploy_judge: `{str(summary['selection']['deploy_judge']).lower()}`",
                f"- selected_candidate: `{summary['selection']['selected_candidate']}`",
                f"- reason: {summary['selection']['reason']}",
                "",
                "## Artifacts",
                "",
                "- `data/eval_runs/judge-agreement-v1/agreement_summary.json`",
                "- `data/eval_runs/judge-agreement-v1/*_verdicts.jsonl`",
                "- `data/eval_runs/judge-agreement-v1/probe_verdicts.jsonl`",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
