# Q1 Execution Spec

This document explains how the frozen Q1 Hard Demo plan is executed without
changing the plan. The task plan is frozen at
`v0.3-q1-hard-demo-plan-freeze` and is not edited except for mechanical
formatting or obvious prose residue.

## Q1 Goal

Build a local, runnable, traceable, and evaluable trustworthy enterprise
document RAG-Agent QA system that demonstrates grounded answers, citation
binding, refusal behavior, document state handling, ACL gates, real reranking,
agentic evidence recovery, baseline comparison, and failure analysis.

## Frozen Constraints (do not relitigate)

1. The task plan is frozen; only Week 4 down-scoping lines apply afterward.
2. Synthetic fixtures are functional regression only - never headline metrics.
3. Mock providers are for CI / unit / smoke only - never reported numbers.
4. The public external corpus is the primary basis for external headline.
5. The headline answer metric is `grounded_correctness`.
6. At least 50% of external eval queries are real human questions.
7. `expected_rewrite` is informational and never scored.
8. The agentic loop is justified only by final_gated vs final_agentic on the
   obfuscated split.
9. `ask_clarification` is not a Q1 response mode.
10. `report_conflict` is kept but only as minimal active-active,
    same-`conflict_group_id` detection.

## Response Modes (frozen)

`answer`, `refuse_no_evidence`, `refuse_permission`, `warn_deprecated`,
`report_conflict`, `system_error`. `ask_clarification` is removed (no ambiguity
detector owns it in Q1). Priority:
`refuse_permission > report_conflict > warn_deprecated > answer/refuse_no_evidence`.
Active vs deprecated in the same group is `warn_deprecated`, not a conflict.

## P0 Must Do

- Keep schemas, eval protocol, corpus protocol, and IDs stable.
- Use real embedding, real reranker, and real LLM for formal Q1 metrics.
- Preserve traceability for retrieval, gates, decisions, and agentic recovery.
- Keep mock providers limited to tests, CI, and smoke tests.
- Protect evaluation and failure analysis from feature creep.

## P1 Optional

- Deeper protocol checks after P0 paths run.
- Richer fixtures after public/hard-negative plans are reviewed.
- Richer trace visualization after trace records stabilize.

## Out Of Scope (Week 0)

No parser/chunker logic, production retrieval, Qdrant, Whoosh, RRF, BGE
reranking, real model calls, Docker, LangGraph, or a complete RAG workflow.

## Out Of Scope (Week 1)

No sentence-transformers, Qdrant, Whoosh, BM25, RRF, BGE reranker, real LLM,
`/chat` main chain, eval runner, Docker, LangGraph, or headline metrics from
fixtures.

## Week 0 Acceptance

- `uv sync` resolves the environment.
- `ruff check .` passes.
- `pytest` passes.
- FastAPI serves `/`, `/health`, and `/docs`.
- Core schemas support JSON round-trip.
- Fixtures and docs clearly state that mock and fixture results are not
  headline metrics.

## Week 1 Acceptance

- Markdown/TXT sample corpus files load in stable path order.
- YAML front matter is parsed into `DocumentMetadata` with English-first
  fallbacks.
- Markdown headings produce stable section paths and line numbers.
- Section-aware chunking writes stable chunk IDs and inherits metadata.
- `data/generated/documents.jsonl`, `data/generated/chunks.jsonl`, and
  `data/generated/chunk_manifest.jsonl` are generated.
- Demo eval `gold_chunk_ids` are backfilled only from real generated chunks.
- `docs/EVAL_CASE_REVIEW_WEEK1.md` exists as a review aid, not a formal report.

## Mock-First Principle

Mock providers are scaffolding for fast local verification (tests, CI, smoke).
They are not valid for formal evaluation, EVALUATION_REPORT claims, or headline
metrics.

## Codex And Claude Split

Codex is the sole code executor for the repository. Claude reviews and drafts
non-code artifacts (corpus, protocols, eval drafts, docs) but does not own code
changes.

## Week 4 Cut Line

Week 4 is the forced scope checkpoint. If real eval, traceability, or failure
analysis are at risk, optional features are cut along the pre-set down-scoping
lines before they consume the remaining evaluation window.
