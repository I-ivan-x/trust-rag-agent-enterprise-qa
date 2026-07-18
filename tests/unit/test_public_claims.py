from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.eval import public_claims
from app.eval.public_claims import load_and_verify_registry, render_public_claims
from app.schemas.public_claims import CleanCloneVerificationReceipt


def test_registry_is_strict_complete_and_generates_all_public_views() -> None:
    registry = load_and_verify_registry()
    assert len(registry.claims) == 14
    assert {claim.question_id for claim in registry.claims} == {"Q1", "Q2", "Q3", "Q4", "Q5"}
    assert registry.q5_overall_status == "scoped_negative_complete"
    rendered = render_public_claims(registry)
    assert set(rendered) == set(public_claims.GENERATED_PATHS)
    for payload in rendered.values():
        assert b"uncovered 32/32" not in payload


def test_zh_cn_presentation_covers_every_claim_and_metric() -> None:
    registry = load_and_verify_registry()
    catalog = public_claims.load_and_verify_presentation_catalog(registry)
    assert len(catalog.claims) == len(registry.claims) == 14
    assert set(catalog.metric_labels) == {
        metric_name for claim in registry.claims for metric_name in claim.metrics
    }
    rendered = render_public_claims(registry, catalog)
    questions = json.loads(rendered[Path("frontend/src/data/questions.json")])
    for question in questions["questions"]:
        for claim in question["claims"]:
            assert claim["presentation"]["canonical_status"] == claim["status"]
            assert claim["presentation"]["headline_eligible"] == claim["headline_eligible"]


@pytest.mark.parametrize(
    "mutation",
    ["missing_claim", "unknown_status", "unknown_metric_label", "unknown_template_metric"],
)
def test_zh_cn_presentation_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    registry = load_and_verify_registry()
    payload = json.loads(public_claims.PRESENTATION_PATH.read_text(encoding="utf-8"))
    if mutation == "missing_claim":
        payload["claims"].pop(registry.claims[0].claim_id)
    elif mutation == "unknown_status":
        payload["status_labels"]["proven"] = "已证明"
    elif mutation == "unknown_metric_label":
        payload["metric_labels"]["invented_metric"] = "虚构指标"
    else:
        payload["claims"][registry.claims[0].claim_id]["summary_template"] += (
            " {invented_metric|fraction}"
        )
    target = tmp_path / "presentation.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    original_tracked = public_claims._is_git_tracked
    monkeypatch.setattr(
        public_claims,
        "_is_git_tracked",
        lambda path: True if Path(path) == target else original_tracked(path),
    )
    with pytest.raises((ValidationError, ValueError)):
        public_claims.load_and_verify_presentation_catalog(registry, target)


def test_frontend_components_do_not_reimplement_claim_semantics() -> None:
    component_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("frontend/src/components").glob("*.astro")
    )
    assert not __import__("re").search(r"switch\s*\([^)]*claim_id", component_source)
    assert not __import__("re").search(r"\b(?:9/9|1/12|32/32|0\.083333)\b", component_source)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_status",
        "unknown_evidence_mode",
        "duplicate_claim_id",
        "missing_numerator",
        "source_hash",
        "source_run_id",
        "execution_commit_type",
        "metric_pointer",
        "metric_numerator",
        "metric_denominator",
        "ambiguous_wording",
    ],
)
def test_registry_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    payload = json.loads(public_claims.REGISTRY_PATH.read_text(encoding="utf-8"))
    if mutation == "unknown_status":
        payload["claims"][0]["status"] = "proven"
    elif mutation == "unknown_evidence_mode":
        payload["claims"][0]["evidence_mode"] = "anecdotal"
    elif mutation == "duplicate_claim_id":
        payload["claims"][1]["claim_id"] = payload["claims"][0]["claim_id"]
    elif mutation == "missing_numerator":
        del payload["claims"][0]["metrics"]["false_answer_rate"]["numerator"]
    elif mutation == "source_hash":
        payload["claims"][0]["source_artifacts"][0]["sha256"] = "0" * 64
    elif mutation == "source_run_id":
        payload["claims"][0]["source_artifacts"][0]["run_id"] = "forged-run"
    elif mutation == "execution_commit_type":
        payload["claims"][0]["source_artifacts"][0]["execution_commit"] = (
            "28c55f81d185fedab1d21a9a7f70af6272aa0b52"
        )
    elif mutation == "metric_pointer":
        payload["claims"][0]["metrics"]["false_answer_rate"]["source"][
            "value_pointer"
        ] = "/summary_metrics/final_gated/missing"
    elif mutation == "metric_numerator":
        metric = payload["claims"][0]["metrics"]["grounded_correctness"]
        metric["numerator"] = 13
        metric["value"] = 0.26
    elif mutation == "metric_denominator":
        metric = payload["claims"][0]["metrics"]["false_answer_rate"]
        metric["denominator"] = 25
    else:
        payload["claims"][0]["public_summary"] += " uncovered 32/32"
    target = tmp_path / "registry.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    original_tracked = public_claims._is_git_tracked
    monkeypatch.setattr(
        public_claims,
        "_is_git_tracked",
        lambda path: True if Path(path) == target else original_tracked(path),
    )
    expected_error = (ValidationError, ValueError)
    with pytest.raises(expected_error):
        load_and_verify_registry(target)


def test_untracked_source_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(public_claims.REGISTRY_PATH.read_text(encoding="utf-8"))
    source_path = payload["claims"][0]["source_artifacts"][0]["path"]
    target = tmp_path / "registry.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    original_tracked = public_claims._is_git_tracked
    monkeypatch.setattr(
        public_claims,
        "_is_git_tracked",
        lambda path: (
            True
            if Path(path) == target
            else False
            if path == source_path
            else original_tracked(path)
        ),
    )
    with pytest.raises(ValueError, match="not Git tracked"):
        load_and_verify_registry(target)


def test_check_mode_detects_drift_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "generated.json"
    target.write_bytes(b"drift\n")
    before = target.read_bytes()
    registry = load_and_verify_registry()
    monkeypatch.setattr(public_claims, "load_and_verify_registry", lambda: registry)
    monkeypatch.setattr(public_claims, "GENERATED_PATHS", (target,))
    monkeypatch.setattr(
        public_claims,
        "render_public_claims",
        lambda _registry, _catalog: {target: b"expected\n"},
    )
    with pytest.raises(ValueError, match="drifted"):
        public_claims.build_public_claims(check=True)
    assert target.read_bytes() == before


def test_presentation_catalog_change_requires_regeneration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = load_and_verify_registry()
    catalog = public_claims.load_and_verify_presentation_catalog(registry)
    first_id = registry.claims[0].claim_id
    mutated_claim = catalog.claims[first_id].model_copy(update={"label": "已修改中文标签"})
    mutated = catalog.model_copy(
        update={"claims": {**catalog.claims, first_id: mutated_claim}}
    )
    monkeypatch.setattr(
        public_claims,
        "load_and_verify_presentation_catalog",
        lambda _registry: mutated,
    )
    with pytest.raises(ValueError, match="generated files drifted"):
        public_claims.build_public_claims(check=True)


def test_not_evaluated_claim_cannot_self_report_metrics() -> None:
    registry = load_and_verify_registry()
    claim = next(item for item in registry.claims if item.claim_id == "q5.open_world_llm_value")
    payload = copy.deepcopy(claim.model_dump(mode="json"))
    payload["metrics"] = {
        "invented": {
            "numerator": 1,
            "denominator": 1,
            "value": 1,
            "unit": "rate",
            "source": {
                "source_path": "data/claims/source/invented/summary.json",
                "derivation": "direct",
                "value_pointer": "/invented",
                "tolerance": 0.001,
            },
        }
    }
    with pytest.raises(ValidationError):
        type(claim).model_validate(payload)


def test_raw_source_numeric_mutation_fails_closed() -> None:
    registry = load_and_verify_registry()
    claim = registry.claims[0]
    metric = claim.metrics["grounded_correctness"]
    payload = json.loads(Path(metric.source.source_path).read_text(encoding="utf-8"))
    payload["summary_metrics"]["final_gated"]["grounded_correctness"] = 0.26
    with pytest.raises(ValueError, match="claim metric numerator mismatch"):
        public_claims._verify_metric_binding(
            claim.claim_id,
            "grounded_correctness",
            metric,
            payload,
        )


def test_import_receipt_and_raw_source_mismatch_fails_closed() -> None:
    registry = load_and_verify_registry()
    audit = public_claims.load_and_verify_source_import_audit()
    source = registry.claims[0].source_artifacts[0]
    row = audit.artifacts[0].model_copy(update={"original_sha256": "0" * 64})
    with pytest.raises(ValueError, match="import audit provenance mismatch"):
        public_claims._verify_import_audit_row(source, row)


def test_tag_object_cannot_masquerade_as_commit() -> None:
    source = load_and_verify_registry().claims[0].source_artifacts[0]
    forged = source.model_copy(update={"tag_object_sha": source.execution_commit})
    with pytest.raises(ValueError, match="not an annotated tag object"):
        public_claims._verify_source_lineage(forged)


def test_artifact_commit_must_contain_source_path() -> None:
    source = load_and_verify_registry().claims[0].source_artifacts[0]
    forged = source.model_copy(update={"artifact_commit": source.execution_commit})
    with pytest.raises(ValueError, match="does not contain source path"):
        public_claims._verify_source_lineage(forged)


def test_execution_commit_must_be_current_history_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = load_and_verify_registry().claims[0].source_artifacts[0]
    monkeypatch.setattr(public_claims, "_is_ancestor", lambda _: False)
    with pytest.raises(ValueError, match="not in the current ancestor chain"):
        public_claims._verify_source_lineage(source)


def test_working_tree_source_must_equal_committed_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = load_and_verify_registry().claims[0].source_artifacts[0]
    monkeypatch.setattr(public_claims, "_committed_blob", lambda *_: b"forged")
    with pytest.raises(ValueError, match="differs from committed blob"):
        public_claims._verify_source_lineage(source)


def test_public_snapshot_rejects_prompt_body_and_secret() -> None:
    with pytest.raises(ValueError, match="prompt text"):
        public_claims._verify_safe_public_snapshot("fixture.json", b'{"prompt":"body"}')
    with pytest.raises(ValueError, match="secret/token"):
        public_claims._verify_safe_public_snapshot(
            "fixture.json",
            b'{"api_key":"sk-forbidden"}',
        )


def test_clean_clone_receipt_rejects_ignored_dependency_claim() -> None:
    payload = {
        "schema_version": "public-claim-clean-clone-receipt-v1",
        "tested_commit": "0" * 40,
        "tested_tree": "1" * 40,
        "claim_count": 14,
        "raw_source_count": 9,
        "source_blob_count": 11,
        "generated_file_count": 9,
        "ignored_file_dependency_count": 1,
        "schema_check": "passed",
        "source_lineage_check": "passed",
        "generator_check": "passed",
    }
    with pytest.raises(ValidationError):
        CleanCloneVerificationReceipt.model_validate(payload)
