# TrustRAG Enterprise QA

TrustRAG Enterprise QA is the Week 0 engineering foundation for the
**Trustworthy Enterprise Document RAG-Agent QA System**. The Q1 goal is a
local, traceable, testable enterprise document QA system that can explain why it
answered, refused, warned on deprecated evidence, or blocked access.

This is not a plain RAG chatbot. The frozen Q1 plan centers on five trust
dimensions - retrieval correctness, citation support, refusal behavior,
state/ACL compliance, and auditability - rather than only "retrieve chunks and
prompt a model."

The RAG-Agent name is justified by a small, workflow-based agentic evidence
recovery loop (query rewrite + one second-pass retrieval), not a free-planning
autonomous agent.

## Trust & Evaluation Discipline

- **Headline metric is `grounded_correctness`** (correct answer + valid,
  supporting citations). Raw answer correctness is reference only.
- Three separate corpora: synthetic fixtures, public external, hard negatives.
  Headline numbers come from the **public external** corpus with real models.
- **Synthetic fixtures and mock runs are never headline metrics** - they are for
  schema, CI, chunking, and smoke checks only.
- Response modes are fixed to `answer`, `refuse_no_evidence`,
  `refuse_permission`, `warn_deprecated`, `report_conflict`, `system_error`.

See `docs/CORPUS_PROTOCOL.md`, `docs/EVAL_PROTOCOL.md`,
`docs/Q1_EXECUTION_SPEC.md`, and `docs/SCHEMA_REVIEW_CHECKLIST.md`.

## Q1 Hard Demo Scope (Week 0-2)

Week 0 only builds the base: FastAPI, settings, shared enums, schemas,
mock-only service placeholders, Northstar Cloud synthetic fixture documents,
demo eval schema data, protocol docs, linting, and tests.

Week 1 adds the ingestion and section-aware chunking path from Markdown/TXT
fixtures to generated JSONL artifacts. It also backfills demo eval
`gold_chunk_ids` from real generated fixture chunks.

Week 2 adds the retrieval base: embedding service interfaces, Whoosh BM25,
Qdrant vector-store wiring, RRF hybrid search, index status, rebuild scripts,
and search preview.

Week 2 still does **not** implement BGE reranking, `/chat`, real LLM calls,
answer generation, citation binding, ACL gates, document state gates, evidence
gates, agentic recovery, Docker, LangGraph, or an eval runner.

MockEmbeddingService and MockLLMClient are for tests, CI, and smoke tests only.
Mock output must not be reported as formal evaluation or headline metrics.
MockEmbeddingService must also not be cited as formal retrieval-eval evidence.
SentenceTransformerEmbeddingService with `BAAI/bge-small-en-v1.5` is the default
direction for formal retrieval evaluation once Qdrant is available.

## Quick Start

```powershell
python -m uv sync
python -m uv run uvicorn app.main:app --reload
```

Open Swagger UI at <http://127.0.0.1:8000/docs>.

## Current Week 2 Status

- FastAPI app and `/health` endpoint are available.
- Pydantic schemas reserve the v0.3 corpus, eval, agentic recovery, and grounded
  scoring fields.
- Five Northstar Cloud synthetic fixtures and a 5-case demo eval exist only for
  schema, chunking, smoke checks, and fixture regression.
- `scripts/ingest_corpus.py` generates `documents.jsonl`, `chunks.jsonl`, and
  `chunk_manifest.jsonl` under `data/generated/`.
- `scripts/rebuild_indexes.py` builds the local Whoosh index and attempts the
  Qdrant vector index.
- `scripts/search_preview.py` previews keyword, vector, or hybrid search.
- If Qdrant is unavailable, Whoosh and RRF tests still run; formal vector
  retrieval requires Qdrant.
- Formal evaluation still requires real embedding, real reranker, and real LLM
  in later weeks.

## Common Commands

```powershell
python -m uv sync
python -m uv run ruff check .
python -m uv run pytest
python -m uv run python scripts/ingest_corpus.py
python -m uv run python scripts/rebuild_indexes.py --embedding-provider mock
python -m uv run python scripts/search_preview.py "refresh token rate limit" --mode keyword
python -m uv run python scripts/search_preview.py "refresh token rate limit" --mode hybrid
python -m uv run uvicorn app.main:app --reload
```
