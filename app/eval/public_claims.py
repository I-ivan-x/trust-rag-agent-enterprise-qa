"""Canonical public-claim verification and deterministic publication views."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from app.schemas.public_claims import ClaimRegistry, ClaimStatus

REGISTRY_PATH = Path("data/claims/claim_registry.json")
GENERATED_PATHS = (
    Path("data/claims/claim_registry.schema.json"),
    Path("docs/Q5_CLAIM_MATRIX.md"),
    Path("docs/Q5_FINAL_REPORT.md"),
    Path("docs/Q5_BOUNDARY_A_F_SUMMARY.md"),
    Path("frontend/src/data/questions.json"),
    Path("frontend/src/data/headline-results.json"),
    Path("frontend/src/data/decision-frontier.json"),
    Path("frontend/src/data/q5-evidence.json"),
    Path("frontend/src/data/engineering-signals.json"),
)
STATUS_LABELS = {
    ClaimStatus.demonstrated_in_frozen_scope: "Demonstrated within the frozen scope",
    ClaimStatus.falsified_in_current_scope: "Falsified in the current scope",
    ClaimStatus.not_evaluated: "Not evaluated",
}
QUESTION_TITLES = {
    "Q1": "Can evidence gates make retrieval-augmented answers safer?",
    "Q2": "Does a bounded agentic recovery loop add measurable value?",
    "Q3": "Can trust gates govern side-effecting actions?",
    "Q4": "Can calibration improve action selection without weakening safety?",
    "Q5": "Where does a selective tool-using agent add value?",
}


def load_and_verify_registry(path: Path | str = REGISTRY_PATH) -> ClaimRegistry:
    registry_path = Path(path)
    if not _is_git_tracked(registry_path.as_posix()):
        raise ValueError("canonical claim registry is not Git tracked")
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry = ClaimRegistry.model_validate(payload)
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    if "uncovered 32/32" in serialized:
        raise ValueError("ambiguous uncovered 32/32 wording is forbidden")
    for claim in registry.claims:
        for source in claim.source_artifacts:
            source_path = Path(source.path)
            if not source_path.is_file():
                raise ValueError(f"claim source artifact is missing: {source.path}")
            if not _is_git_tracked(source.path):
                raise ValueError(f"claim source artifact is not Git tracked: {source.path}")
            actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if actual_hash != source.sha256:
                raise ValueError(f"claim source artifact hash mismatch: {source.path}")
            if not _commit_exists(source.evidence_commit):
                raise ValueError(f"claim evidence commit does not exist: {source.evidence_commit}")
            _verify_source_identity(claim.evidence_mode.value, claim.split_or_frozen_scope, source)
    return registry


def render_public_claims(registry: ClaimRegistry) -> dict[Path, bytes]:
    claims = [_public_claim(claim) for claim in registry.claims]
    by_question = {
        question_id: [claim for claim in claims if claim["question_id"] == question_id]
        for question_id in QUESTION_TITLES
    }
    question_status = {
        "Q1": "demonstrated_in_frozen_scope",
        "Q2": "falsified_in_current_scope",
        "Q3": "mixed_scoped_results",
        "Q4": "demonstrated_in_frozen_scope",
        "Q5": registry.q5_overall_status,
    }
    questions = {
        "schema_version": "public-question-data-v1",
        "project": registry.project_public_name,
        "questions": [
            {
                "question_id": question_id,
                "question": title,
                "status": question_status[question_id],
                "claim_ids": [claim["claim_id"] for claim in by_question[question_id]],
                "claims": by_question[question_id],
            }
            for question_id, title in QUESTION_TITLES.items()
        ],
    }
    headlines = {
        "schema_version": "public-headline-results-v1",
        "claims": [claim for claim in claims if claim["headline_eligible"]],
    }
    frontier = {
        "schema_version": "public-decision-frontier-v1",
        "segments": [
            {
                "segment_id": "grammar",
                "label": "Grammar",
                "claim_ids": ["q5.controlled_prose_llm_necessity"],
                "interpretation": "Closed grammars remain a deterministic-parser responsibility.",
            },
            {
                "segment_id": "controlled_prose",
                "label": "Controlled prose",
                "claim_ids": ["q5.controlled_prose_llm_necessity"],
                "interpretation": "The frozen 32-case controlled-prose track is closed.",
            },
            {
                "segment_id": "open_semantics",
                "label": "Open semantics",
                "claim_ids": ["q5.llm_semantic_uplift", "q5.open_world_llm_value"],
                "interpretation": (
                    "Current-scope uplift failed; open-world value remains unevaluated."
                ),
            },
            {
                "segment_id": "unsafe",
                "label": "Unsafe",
                "claim_ids": ["q5.schema_transition_safety"],
                "interpretation": "Unsafe or ungrounded transitions remain fail-closed.",
            },
        ],
        "claims": [claim for claim in claims if claim["question_id"] == "Q5"],
    }
    q5 = {
        "schema_version": "public-q5-evidence-v1",
        "overall_status": registry.q5_overall_status,
        "controlled_prose_track": "closed",
        "k1_approved": False,
        "boundary_g_allowed": False,
        "new_k1_data_allowed": False,
        "claims": by_question["Q5"],
    }
    signals = {
        "schema_version": "public-engineering-signals-v1",
        "signals": [
            claim
            for claim in claims
            if claim["claim_id"]
            in {
                "q1.fail_closed_answers",
                "q3.action_safety",
                "q4.release_reliability",
                "q5.observation_adaptation",
                "q5.schema_transition_safety",
                "q5.hybrid_efficiency",
            }
        ],
    }
    return {
        Path("data/claims/claim_registry.schema.json"): _json_bytes(
            ClaimRegistry.model_json_schema()
        ),
        Path("docs/Q5_CLAIM_MATRIX.md"): _claim_matrix(registry).encode(),
        Path("docs/Q5_FINAL_REPORT.md"): _q5_final_report(registry).encode(),
        Path("docs/Q5_BOUNDARY_A_F_SUMMARY.md"): _boundary_summary(registry).encode(),
        Path("frontend/src/data/questions.json"): _json_bytes(questions),
        Path("frontend/src/data/headline-results.json"): _json_bytes(headlines),
        Path("frontend/src/data/decision-frontier.json"): _json_bytes(frontier),
        Path("frontend/src/data/q5-evidence.json"): _json_bytes(q5),
        Path("frontend/src/data/engineering-signals.json"): _json_bytes(signals),
    }


def build_public_claims(*, check: bool = False) -> dict[str, int]:
    registry = load_and_verify_registry()
    rendered = render_public_claims(registry)
    if set(rendered) != set(GENERATED_PATHS):
        raise ValueError("public claim generated-file contract mismatch")
    drift = []
    for path, expected in rendered.items():
        if check:
            if not path.is_file() or path.read_bytes() != expected:
                drift.append(path.as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
    if drift:
        raise ValueError("public claim generated files drifted: " + ", ".join(drift))
    source_count = len(
        {source.path for claim in registry.claims for source in claim.source_artifacts}
    )
    return {
        "claim_count": len(registry.claims),
        "source_artifact_count": source_count,
        "generated_file_count": len(rendered),
    }


def _public_claim(claim) -> dict[str, Any]:
    payload = claim.model_dump(mode="json")
    payload["status_label"] = STATUS_LABELS[claim.status]
    return payload


def _claim_matrix(registry: ClaimRegistry) -> str:
    lines = [
        "# Q5 Claim Matrix",
        "",
        "Generated from `data/claims/claim_registry.json`; do not edit by hand.",
        "",
        f"Overall Q5 status: `{registry.q5_overall_status}`.",
        "",
        "| Claim | Public conclusion | Scope | Evidence | Headline |",
        "| --- | --- | --- | --- | --- |",
    ]
    for claim in registry.claims:
        if claim.question_id != "Q5":
            continue
        sources = "<br>".join(
            f"`{source.path}` (`{source.run_id}`)" for source in claim.source_artifacts
        )
        lines.append(
            f"| `{claim.claim_id}` — {claim.public_label} | {STATUS_LABELS[claim.status]} | "
            f"{claim.claim_scope} | {sources} | {'yes' if claim.headline_eligible else 'no'} |"
        )
    lines.extend(
        [
            "",
            "The controlled-prose track is closed. K1, Boundary G, and new K1 data are not "
            "authorized. Open-world LLM value is not evaluated.",
        ]
    )
    return "\n".join(lines) + "\n"


def _q5_final_report(registry: ClaimRegistry) -> str:
    by_id = {claim.claim_id: claim for claim in registry.claims}
    controlled = by_id["q5.controlled_prose_llm_necessity"]
    architecture = by_id["q5.selective_runtime_architecture"]
    efficiency = by_id["q5.hybrid_efficiency"]
    uplift = by_id["q5.llm_semantic_uplift"]
    return (
        "\n".join(
            [
                "# Q5 Final Report",
                "",
                "Generated from `data/claims/claim_registry.json`; do not edit numeric claims by hand.",
                "",
                f"Overall status: `{registry.q5_overall_status}`.",
                "",
                "## Formal conclusion",
                "",
                "Q5 demonstrated a bounded selective runtime, observation completion, schema and "
                "transition safety, and hybrid efficiency within their named real-dev scopes. It "
                "did not demonstrate the preregistered LLM semantic uplift, and deterministic "
                "controls closed the frozen controlled-prose track. Open-world LLM value remains "
                "not evaluated.",
                "",
                "## Sequential Boundary F evidence",
                "",
                f"The original Boundary F evidence remains {_fraction(controlled, 'original_boundary_f_coverage')} "
                "coverage. The later addendum is a separate evidence layer; it does not overwrite "
                "the historical artifact.",
                "",
                "Addendum metrics within the frozen K0U parser-uncovered 32-case scope:",
                "",
                f"- previously_uncovered_cases_resolved: {_fraction(controlled, 'previously_uncovered_cases_resolved')}",
                f"- remaining_uncovered_cases: {_fraction(controlled, 'remaining_uncovered')}",
                f"- coverage: {_value(controlled, 'addendum_coverage'):.1f}",
                f"- conditional_risk: {_value(controlled, 'addendum_conditional_risk'):.1f}",
                f"- abstention_count: {int(controlled.metrics['addendum_abstention_count'].numerator)}",
                "",
                "`controlled_prose_track=closed`; `K1=false`; Boundary G and new K1 data are not "
                "authorized.",
                "",
                "## Real-run and request boundary",
                "",
                f"The historical protocol-v3 primary real-dev run made "
                f"{int(architecture.metrics['historical_real_dev_model_calls'].value)} model calls. "
                f"Its Hybrid/LLM-only call ratio was {_fraction(efficiency, 'model_call_ratio')} and "
                f"token ratio was {_fraction(efficiency, 'token_ratio')}. The Boundary F addendum "
                f"made {int(controlled.metrics['addendum_model_requests'].value)} model requests and "
                f"{int(controlled.metrics['addendum_external_requests'].value)} external requests.",
                "",
                f"The semantic uplift was {_fraction(uplift, 'semantic_uplift')}, below the frozen "
                "0.10 value threshold. This is a current-scope negative result, not a claim that "
                "LLMs are generally without value.",
                "",
                "No `q5_test` split was created or read during closure. The latest stable product "
                "release remains `v3.0-q4-reliability`; Q5 does not create a release or tag.",
                "",
                "## Evidence boundary",
                "",
                "Every number above is generated from registry claim IDs and hash-bound source "
                "artifacts. See `docs/Q5_CLAIM_MATRIX.md` for the per-claim evidence mapping.",
            ]
        )
        + "\n"
    )


def _boundary_summary(registry: ClaimRegistry) -> str:
    controlled = next(
        claim for claim in registry.claims if claim.claim_id == "q5.controlled_prose_llm_necessity"
    )
    return (
        "\n".join(
            [
                "# Q5 Boundary A-F Summary",
                "",
                "This is a current public summary, not a replacement for historical artifacts.",
                "",
                "| Boundary | Interpretation | Public evidence role |",
                "| --- | --- | --- |",
                "| A | Explicit closed grammar was deterministic. | Historical diagnostic boundary. |",
                "| B | Controlled prose remained inside an ordinary parser extension. | Historical diagnostic boundary. |",
                "| C | A compositional challenger recovered the remaining template family. | Historical diagnostic boundary. |",
                "| D | A label shortcut invalidated the apparent headroom. | Historical diagnostic boundary. |",
                "| E | K0T controlled templates remained deterministic. | Historical diagnostic boundary. |",
                f"| F | Runtime-only parsing reached {_fraction(controlled, 'original_boundary_f_coverage')}; "
                f"the versioned addendum then reached {_fraction(controlled, 'addendum_parser_accuracy')} "
                "in the frozen 32-case scope. | Current tracked controlled-prose evidence. |",
                "",
                "The original Boundary F and addendum are sequential evidence layers and remain "
                "separate. Their tracked source hashes are recorded under claim "
                "`q5.controlled_prose_llm_necessity`.",
                "",
                "The controlled-prose track is closed. This does not evaluate open-world LLM value, "
                "does not approve K1, and does not authorize Boundary G or new K1 data.",
            ]
        )
        + "\n"
    )


def _fraction(claim, metric_name: str) -> str:
    metric = claim.metrics[metric_name]
    return f"{_number(metric.numerator)}/{_number(metric.denominator)}"


def _value(claim, metric_name: str) -> float:
    return claim.metrics[metric_name].value


def _number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _verify_source_identity(evidence_mode: str, scope: str, source) -> None:
    try:
        payload = json.loads(Path(source.path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"claim source artifact is not JSON: {source.path}") from exc
    embedded_run_ids = set()
    if isinstance(payload, dict) and payload.get("run_id") is not None:
        embedded_run_ids.add(payload["run_id"])
    if isinstance(payload, dict):
        embedded_run_ids.update(
            item.get("run_id")
            for item in payload.get("source_runs", [])
            if isinstance(item, dict) and item.get("run_id")
        )
    if embedded_run_ids and source.run_id not in embedded_run_ids:
        raise ValueError(f"claim source run ID mismatch: {source.path}")
    embedded_mode = payload.get("evidence_mode") if isinstance(payload, dict) else None
    if embedded_mode is not None and embedded_mode != evidence_mode:
        raise ValueError(f"claim source evidence mode mismatch: {source.path}")
    embedded_scope = payload.get("split") if isinstance(payload, dict) else None
    if embedded_scope is not None and embedded_scope not in scope and scope not in embedded_scope:
        raise ValueError(f"claim source scope mismatch: {source.path}")


def _is_git_tracked(path: str) -> bool:
    return (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _commit_exists(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
