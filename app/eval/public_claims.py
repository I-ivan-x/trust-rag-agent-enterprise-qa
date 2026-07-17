"""Canonical public-claim verification and deterministic publication views."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from functools import cache
from pathlib import Path
from typing import Any

from app.schemas.public_claims import (
    ClaimMetric,
    ClaimRegistry,
    ClaimSourceArtifact,
    ClaimStatus,
    MetricDerivation,
    SourceImportAudit,
)

REGISTRY_PATH = Path("data/claims/claim_registry.json")
SOURCE_IMPORT_AUDIT_PATH = Path("data/claims/source_import_audit.json")
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
    audit = load_and_verify_source_import_audit()
    audited_sources = {row.source_path: row for row in audit.artifacts}
    raw_payloads: dict[str, Any] = {}
    for claim in registry.claims:
        claim_source_paths = {source.path for source in claim.source_artifacts}
        for source in claim.source_artifacts:
            source_path = Path(source.path)
            if not source_path.is_file():
                raise ValueError(f"claim source artifact is missing: {source.path}")
            if not _is_git_tracked(source.path):
                raise ValueError(f"claim source artifact is not Git tracked: {source.path}")
            actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if actual_hash != source.sha256:
                raise ValueError(f"claim source artifact hash mismatch: {source.path}")
            _verify_source_lineage(source)
            if source.path.startswith("data/claims/source/"):
                _verify_import_audit_row(source, audited_sources.get(source.path))
            _verify_source_identity(claim.evidence_mode.value, claim.split_or_frozen_scope, source)
            raw_payloads[source.path] = _load_json(source.path)
        for metric_name, metric in claim.metrics.items():
            if metric.source.source_path not in claim_source_paths:
                raise ValueError(
                    f"claim metric source is not declared by the claim: {claim.claim_id}.{metric_name}"
                )
            payload = raw_payloads.setdefault(
                metric.source.source_path,
                _load_json(metric.source.source_path),
            )
            _verify_metric_binding(claim.claim_id, metric_name, metric, payload)
    imported_sources = {
        source.path
        for claim in registry.claims
        for source in claim.source_artifacts
        if source.path.startswith("data/claims/source/")
    }
    if imported_sources != set(audited_sources):
        raise ValueError("source import audit closure does not match registry raw sources")
    return registry


def load_and_verify_source_import_audit(
    path: Path | str = SOURCE_IMPORT_AUDIT_PATH,
) -> SourceImportAudit:
    audit_path = Path(path)
    if not audit_path.is_file() or not _is_git_tracked(audit_path.as_posix()):
        raise ValueError("source import audit is missing or not Git tracked")
    audit = SourceImportAudit.model_validate(_load_json(audit_path.as_posix()))
    for row in audit.artifacts:
        source = Path(row.source_path)
        if not source.is_file() or not _is_git_tracked(row.source_path):
            raise ValueError(
                f"audited raw source is missing or not Git tracked: {row.source_path}"
            )
        raw = source.read_bytes()
        if len(raw) != row.size_bytes:
            raise ValueError(f"audited raw source size mismatch: {row.source_path}")
        if hashlib.sha256(raw).hexdigest() != row.original_sha256:
            raise ValueError(f"source import receipt hash mismatch: {row.source_path}")
        _verify_safe_public_snapshot(row.source_path, raw)
    return audit


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
        "source_blob_count": source_count,
        "imported_snapshot_count": len(
            {
                source.path
                for claim in registry.claims
                for source in claim.source_artifacts
                if source.path.startswith("data/claims/source/")
            }
        ),
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


def _verify_source_identity(
    evidence_mode: str,
    scope: str,
    source: ClaimSourceArtifact,
) -> None:
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


def _verify_source_lineage(source: ClaimSourceArtifact) -> None:
    if _object_type(source.execution_commit) != "commit":
        raise ValueError(f"execution_commit is not a commit: {source.execution_commit}")
    if not _is_ancestor(source.execution_commit):
        raise ValueError(f"execution_commit is not in the current ancestor chain: {source.path}")
    if _object_type(source.artifact_commit) != "commit":
        raise ValueError(f"artifact_commit is not a commit: {source.artifact_commit}")
    committed = _committed_blob(source.artifact_commit, source.path)
    if committed is None:
        raise ValueError(f"artifact_commit does not contain source path: {source.path}")
    working = Path(source.path).read_bytes()
    if committed != working:
        raise ValueError(f"working-tree source differs from committed blob: {source.path}")
    if source.release_tag is None:
        return
    if _object_type(source.tag_object_sha or "") != "tag":
        raise ValueError(f"tag_object_sha is not an annotated tag object: {source.path}")
    if _object_type(source.release_commit or "") != "commit":
        raise ValueError(f"release_commit is not a commit: {source.path}")
    tag_object = _git_text("rev-parse", f"refs/tags/{source.release_tag}")
    if tag_object != source.tag_object_sha:
        raise ValueError(f"release tag object mismatch: {source.path}")
    peeled = _git_text("rev-parse", f"{source.release_tag}^{{commit}}")
    if peeled != source.release_commit:
        raise ValueError(f"release tag peel mismatch: {source.path}")


def _verify_import_audit_row(source: ClaimSourceArtifact, row) -> None:
    if row is None:
        raise ValueError(f"raw source is absent from import audit: {source.path}")
    expected = {
        "source_path": source.path,
        "archived_from_path": source.archived_from_path,
        "original_sha256": source.sha256,
        "run_id": source.run_id,
        "execution_commit": source.execution_commit,
        "artifact_import_commit": source.artifact_commit,
    }
    actual = row.model_dump(include=set(expected))
    if actual != expected:
        raise ValueError(f"source import audit provenance mismatch: {source.path}")


def _verify_metric_binding(
    claim_id: str,
    metric_name: str,
    metric: ClaimMetric,
    payload: Any,
) -> None:
    source = metric.source
    tolerance = source.tolerance
    if source.derivation is MetricDerivation.direct:
        value = _number_at(payload, source.value_pointer)
        expected = (value, 1.0, value)
    elif source.derivation is MetricDerivation.boolean:
        raw = _pointer(payload, source.value_pointer)
        if not isinstance(raw, bool):
            raise ValueError(f"boolean metric pointer is not boolean: {claim_id}.{metric_name}")
        value = float(raw)
        expected = (value, 1.0, value)
    elif source.derivation is MetricDerivation.ratio:
        numerator = _number_at(payload, source.numerator_pointer)
        denominator = _positive_number_at(payload, source.denominator_pointer)
        value = numerator / denominator
        if source.value_pointer is not None:
            _assert_close(
                _number_at(payload, source.value_pointer),
                value,
                tolerance,
                f"raw ratio value mismatch: {claim_id}.{metric_name}",
            )
        expected = (numerator, denominator, value)
    elif source.derivation is MetricDerivation.rate_from_value:
        value = _number_at(payload, source.value_pointer)
        denominator = _positive_number_at(payload, source.denominator_pointer)
        expected = (value * denominator, denominator, value)
    else:
        left = _number_at(payload, source.left_pointer)
        right = _number_at(payload, source.right_pointer)
        denominator = _positive_number_at(payload, source.denominator_pointer)
        value = left - right
        if source.value_pointer is not None:
            _assert_close(
                _number_at(payload, source.value_pointer),
                value,
                tolerance,
                f"raw difference value mismatch: {claim_id}.{metric_name}",
            )
        expected = (value * denominator, denominator, value)
    for label, actual, derived in zip(
        ("numerator", "denominator", "value"),
        (metric.numerator, metric.denominator, metric.value),
        expected,
        strict=True,
    ):
        _assert_close(
            actual,
            derived,
            tolerance,
            f"claim metric {label} mismatch: {claim_id}.{metric_name}",
        )


def _pointer(payload: Any, pointer: str | None) -> Any:
    if pointer is None or not pointer.startswith("/"):
        raise ValueError("metric source pointer is missing")
    current = payload
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ValueError(f"JSON pointer does not resolve: {pointer}")
    return current


def _number_at(payload: Any, pointer: str | None) -> float:
    value = _pointer(payload, pointer)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"JSON pointer is not a finite number: {pointer}")
    return float(value)


def _positive_number_at(payload: Any, pointer: str | None) -> float:
    value = _number_at(payload, pointer)
    if value <= 0:
        raise ValueError(f"metric denominator pointer is not positive: {pointer}")
    return value


def _assert_close(actual: float, expected: float, tolerance: float, message: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance):
        raise ValueError(message)


def _load_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"claim source artifact is not JSON: {path}") from exc


def _verify_safe_public_snapshot(path: str, raw: bytes) -> None:
    if len(raw) > 1_000_000:
        raise ValueError(f"public source exceeds the 1 MB publication boundary: {path}")
    text = raw.decode("utf-8")
    forbidden = {
        "secret/token": r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password|private[_-]?key|bearer\s+[A-Za-z0-9._-]+)",
        "email": r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "personal path": r"(?i)([A-Z]:\\Users\\|/home/[^/]+/)",
    }
    for label, pattern in forbidden.items():
        if re.search(pattern, text):
            raise ValueError(f"public source {label} scan failed: {path}")
    payload = json.loads(text)
    _verify_prompt_publication_boundary(payload, path)


def _verify_prompt_publication_boundary(payload: Any, path: str) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in {"prompt", "system_prompt", "user_prompt"}:
                if not (
                    key.lower() == "prompt"
                    and isinstance(value, dict)
                    and set(value) <= {"sha256", "version"}
                    and set(value) == {"sha256", "version"}
                ):
                    raise ValueError(f"public source contains prompt text: {path}")
            _verify_prompt_publication_boundary(value, path)
    elif isinstance(payload, list):
        for value in payload:
            _verify_prompt_publication_boundary(value, path)


@cache
def _object_type(oid: str) -> str | None:
    result = subprocess.run(["git", "cat-file", "-t", oid], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


@cache
def _is_ancestor(commit: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        capture_output=True,
    ).returncode == 0


@cache
def _committed_blob(commit: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{path}"],
        capture_output=True,
    )
    return result.stdout if result.returncode == 0 else None


@cache
def _git_text(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
