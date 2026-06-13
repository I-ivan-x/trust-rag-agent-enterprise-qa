from __future__ import annotations

import json
import random
from hashlib import sha256
from pathlib import Path

SAMPLE_PATH = Path("data/citation_audit/manual_audit_v1_sample.jsonl")
RUN_IDS = [
    "week7-audit-external-final-agentic",
    "week7-audit-obfuscated-final-agentic",
]


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _expected_units() -> list[tuple[str, str, int]]:
    units: list[tuple[str, str, int]] = []
    for run_id in RUN_IDS:
        rows = _read_jsonl(Path("data/eval_runs") / run_id / "answers.jsonl")
        for answer in rows:
            if answer["refused"]:
                continue
            for claim_index, _claim in enumerate(answer["claims"]):
                units.append((run_id, answer["case_id"], claim_index))
    units.sort(key=lambda item: (RUN_IDS.index(item[0]), item[1], item[2]))
    random.Random(42).shuffle(units)
    return units


def test_manual_audit_v1_sample_is_frozen_census() -> None:
    rows = _read_jsonl(SAMPLE_PATH)

    assert len(rows) == 15
    assert sum(row["eval_split"] == "external" for row in rows) == 13
    assert sum(row["eval_split"] == "obfuscated" for row in rows) == 2
    assert not any(row["eval_split"] == "hard_negative" for row in rows)
    assert [row["audit_id"] for row in rows] == [
        f"AUD-{index:03d}" for index in range(1, 16)
    ]
    assert [
        (row["run_id"], row["case_id"], row["claim_index"]) for row in rows
    ] == _expected_units()


def test_manual_audit_v1_sample_has_protocol_fields_and_dates() -> None:
    required = {
        "audit_id",
        "run_id",
        "case_id",
        "system",
        "eval_split",
        "claim_index",
        "claim_text",
        "citation_chunk_ids",
        "cited_text_snapshot_sha256",
        "label",
        "wrong_side_citation",
        "notes",
        "pass",
        "labeled_at",
        "cited_text_snapshot",
        "cited_text_sha256",
        "freeze_date",
        "relabel_due_date",
    }

    for row in _read_jsonl(SAMPLE_PATH):
        assert required <= set(row)
        assert row["freeze_date"] == "2026-06-12"
        assert row["relabel_due_date"] == "2026-06-19"
        assert row["system"] == "final_agentic"
        assert row["label"] is None
        assert row["wrong_side_citation"] is None
        assert row["pass"] == "initial"
        assert row["labeled_at"] is None


def test_manual_audit_v1_sample_sha_matches_answers_jsonl() -> None:
    answers_by_key: dict[tuple[str, str, int], dict] = {}
    for run_id in RUN_IDS:
        rows = _read_jsonl(Path("data/eval_runs") / run_id / "answers.jsonl")
        for answer in rows:
            if answer["refused"]:
                continue
            for claim_index, claim in enumerate(answer["claims"]):
                answers_by_key[(run_id, answer["case_id"], claim_index)] = {
                    "claim": claim,
                    "answer": answer,
                }

    for row in _read_jsonl(SAMPLE_PATH):
        key = (row["run_id"], row["case_id"], row["claim_index"])
        source = answers_by_key[key]
        answer = source["answer"]
        claim = source["claim"]
        assert row["claim_text"] == claim["text"]
        assert row["citation_chunk_ids"] == claim["supporting_chunk_ids"]
        assert row["cited_text_snapshot"] == {
            chunk_id: answer["cited_chunk_texts"][chunk_id]
            for chunk_id in row["citation_chunk_ids"]
        }
        assert row["cited_text_sha256"] == {
            chunk_id: answer["cited_text_sha256"][chunk_id]
            for chunk_id in row["citation_chunk_ids"]
        }
        assert row["cited_text_snapshot_sha256"] == [
            row["cited_text_sha256"][chunk_id]
            for chunk_id in row["citation_chunk_ids"]
        ]
        for chunk_id, text in row["cited_text_snapshot"].items():
            assert text is not None
            assert sha256(text.encode("utf-8")).hexdigest() == row[
                "cited_text_sha256"
            ][chunk_id]
