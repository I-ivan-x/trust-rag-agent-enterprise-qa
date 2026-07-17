from __future__ import annotations

import json

from app.eval.public_claims import GENERATED_PATHS, build_public_claims


def test_generated_public_claim_files_are_current_and_provenanced() -> None:
    result = build_public_claims(check=True)
    assert result == {
        "claim_count": 14,
        "source_artifact_count": 11,
        "source_blob_count": 11,
        "imported_snapshot_count": 9,
        "generated_file_count": 9,
    }
    for path in GENERATED_PATHS:
        assert path.is_file()
    questions = json.loads(
        next(path for path in GENERATED_PATHS if path.name == "questions.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["question_id"] for item in questions["questions"]] == [
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        "Q5",
    ]
    for question in questions["questions"]:
        for claim in question["claims"]:
            assert claim["source_artifacts"]
            assert all(source["sha256"] for source in claim["source_artifacts"])
            assert all(source["execution_commit"] for source in claim["source_artifacts"])
            assert all(source["artifact_commit"] for source in claim["source_artifacts"])
            for metric in claim["metrics"].values():
                assert metric["source"]["source_path"]
                assert metric["source"]["derivation"]


def test_recruiting_data_contract_is_complete_and_scoped() -> None:
    metadata_fields = {
        "claim_id",
        "claim_scope",
        "evidence_mode",
        "headline_eligible",
        "source_artifacts",
        "split_or_frozen_scope",
    }
    data_paths = {
        path.name: path
        for path in GENERATED_PATHS
        if path.suffix == ".json" and "frontend" in path.parts
    }
    assert set(data_paths) == {
        "questions.json",
        "headline-results.json",
        "decision-frontier.json",
        "q5-evidence.json",
        "engineering-signals.json",
    }
    for path in data_paths.values():
        payload = json.loads(path.read_text(encoding="utf-8"))
        claims = payload.get("claims") or payload.get("signals") or [
            claim
            for question in payload.get("questions", [])
            for claim in question["claims"]
        ]
        assert claims, path
        for claim in claims:
            assert metadata_fields <= claim.keys(), (path, claim["claim_id"])
            assert claim["source_artifacts"], (path, claim["claim_id"])
            for source in claim["source_artifacts"]:
                assert {
                    "path",
                    "archived_from_path",
                    "sha256",
                    "run_id",
                    "execution_commit",
                    "artifact_commit",
                } <= source.keys()
    frontier = json.loads(data_paths["decision-frontier.json"].read_text(encoding="utf-8"))
    assert frontier["schema_version"] == "public-decision-frontier-v2"
    assert [segment["segment_id"] for segment in frontier["segments"]] == [
        "grammar",
        "controlled_prose",
        "open_semantics",
        "unsafe",
    ]
    for segment in frontier["segments"]:
        assert {
            "route",
            "parser_status",
            "llm_called",
            "evidence_basis",
            "terminal_outcome",
            "claim_status",
            "states",
        } <= segment.keys()
        assert set(segment["states"]) == {
            "hypothesis",
            "real_result",
            "final_decision",
        }
