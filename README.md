# TrustRAG Enterprise QA

TrustRAG Enterprise QA is the Week 0 engineering foundation for the
Trustworthy Enterprise Document RAG-Agent QA System. The short Q1 goal is a
local, traceable, testable enterprise document QA system that can explain why it
answered, refused, warned on deprecated evidence, or blocked access.

This is not a plain RAG chatbot. The frozen Q1 plan is centered on evidence
quality, ACL behavior, document state gates, citation verification, trace
records, and evaluation discipline rather than only "retrieve chunks and prompt
a model."

The project keeps the RAG-Agent name because the Q1 design includes a small,
workflow-based agentic evidence recovery loop. It is not a free-planning
autonomous agent.

## Q1 Hard Demo Scope

Week 0 only builds the project base: FastAPI, settings, shared enums, schemas,
mock-only service placeholders, synthetic fixture documents, demo eval schema
data, protocol docs, linting, and tests.

Week 0 does not implement parser/chunker logic, Qdrant, Whoosh, RRF, BGE
reranking, real embeddings, real LLM calls, Docker, LangGraph, or the complete
RAG workflow.

MockEmbeddingService and MockLLMClient are for tests, CI, and smoke tests only.
Mock output must not be reported as formal evaluation or headline metrics.

## Quick Start

```bash
uv sync
uvicorn app.main:app --reload
```

Open Swagger UI at <http://127.0.0.1:8000/docs>.

## Current Week 0 Status

- FastAPI app and `/health` endpoint are available.
- Pydantic schemas reserve the v0.3 corpus, eval, agentic recovery, and grounded
  scoring fields.
- Synthetic fixture corpus and demo eval JSONL exist only for schema and smoke
  checks.
- Formal evaluation still requires real embedding, real reranker, and real LLM
  providers in later weeks.

## Common Commands

```bash
uv sync
ruff check .
pytest
uvicorn app.main:app --reload
```

