from __future__ import annotations

import json

from app.eval.public_claims import GENERATED_PATHS, build_public_claims


def test_generated_public_claim_files_are_current_and_provenanced() -> None:
    result = build_public_claims(check=True)
    assert result == {
        "claim_count": 14,
        "source_artifact_count": 7,
        "generated_file_count": 7,
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
            assert all(source["evidence_commit"] for source in claim["source_artifacts"])
