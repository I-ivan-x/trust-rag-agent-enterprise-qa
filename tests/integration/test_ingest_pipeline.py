import json
from pathlib import Path

from app.schemas.chunk import Chunk
from app.schemas.eval import EvalCase
from scripts.ingest_corpus import run_ingest


def test_ingest_pipeline_writes_jsonl_and_backfills_eval(tmp_path: Path) -> None:
    input_dir = tmp_path / "corpus"
    output_dir = tmp_path / "generated"
    eval_path = tmp_path / "demo_eval.jsonl"
    review_path = tmp_path / "review.md"
    input_dir.mkdir()

    (input_dir / "one.md").write_text(
        """---
doc_id: doc-one
title: One
doc_type: api_spec
status: active
version: v1
allowed_roles:
  - employee
---

# One

## Answer
Alpha answer lives here.
""",
        encoding="utf-8",
    )
    (input_dir / "two.md").write_text(
        """---
doc_id: doc-two
title: Two
doc_type: handbook
status: active
version: v1
allowed_roles:
  - employee
---

# Two
Beta content lives here.
""",
        encoding="utf-8",
    )
    eval_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "case-001",
                        "query": "Where does alpha answer live?",
                        "query_type": "single_doc_fact",
                        "eval_split": "fixture",
                        "corpus_source": "synthetic_fixture",
                        "query_source": "manifest_authored",
                        "query_style": "standard",
                        "user_role": "employee",
                        "user_department": "Engineering",
                        "user_clearance": "internal",
                        "expected_behavior": "answer",
                        "gold_doc_ids": ["doc-one"],
                        "gold_chunk_ids": [],
                        "requires_real_model": False,
                    }
                ),
                json.dumps(
                    {
                        "case_id": "case-002",
                        "query": "Missing evidence?",
                        "query_type": "no_evidence",
                        "eval_split": "fixture",
                        "corpus_source": "synthetic_fixture",
                        "query_source": "manifest_authored",
                        "query_style": "standard",
                        "user_role": "employee",
                        "user_department": "Engineering",
                        "user_clearance": "internal",
                        "expected_behavior": "refuse_no_evidence",
                        "gold_doc_ids": [],
                        "gold_chunk_ids": [],
                        "requires_real_model": False,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_ingest(input_dir, output_dir, eval_path=eval_path, review_path=review_path)

    documents_path = output_dir / "documents.jsonl"
    chunks_path = output_dir / "chunks.jsonl"
    manifest_path = output_dir / "chunk_manifest.jsonl"
    assert result["loaded_files"] == 2
    assert documents_path.exists()
    assert chunks_path.exists()
    assert manifest_path.exists()
    assert review_path.exists()

    chunk_records = [
        Chunk.model_validate_json(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    chunk_ids = [chunk.chunk_id for chunk in chunk_records]
    assert len(chunk_ids) == len(set(chunk_ids))

    cases = [
        EvalCase.model_validate_json(line)
        for line in eval_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert cases[0].gold_chunk_ids
    assert cases[1].gold_chunk_ids == []

