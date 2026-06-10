# Q1 Execution Spec

This document explains how the frozen Q1 Hard Demo plan is executed without
changing the plan itself. The task plan is frozen at
`v0.3-q1-hard-demo-plan-freeze` and should not be edited except for mechanical
formatting or obvious prose residue.

## Q1 Goal

Build a local, runnable, traceable, and evaluable trustworthy enterprise
document RAG-Agent QA system that demonstrates grounded answers, citation
binding, refusal behavior, document state handling, ACL gates, real reranking,
agentic evidence recovery, baseline comparison, and failure analysis.

## P0 Must Do

- Keep schemas, eval protocol, corpus protocol, and IDs stable.
- Use real embedding, real reranker, and real LLM paths for formal Q1 metrics.
- Preserve traceability for retrieval, gates, decisions, and agentic recovery.
- Keep mock providers limited to tests, CI, and smoke tests.
- Protect evaluation and failure analysis from feature creep.

## P1 Optional

- Add deeper protocol checks after P0 paths are runnable.
- Improve fixture richness after public external and hard negative corpus plans
  are reviewed.
- Add richer trace visualization after trace records are stable.

## Out Of Scope

Week 0 does not implement parser/chunker logic, production retrieval,
Qdrant, Whoosh, RRF, BGE reranking, real model calls, Docker, LangGraph, or a
complete RAG workflow.

## Week 0 Acceptance

- `uv sync` resolves the Python environment.
- `ruff check .` passes.
- `pytest` passes.
- FastAPI serves `/`, `/health`, and `/docs`.
- Core schemas support JSON round-trip.
- Demo fixtures and docs clearly state that mock results are not headline
  metrics.

## Mock-First Principle

Mock providers are scaffolding for fast local verification. They are allowed in
tests, CI, and smoke checks. They are not valid for formal evaluation,
EVALUATION_REPORT claims, or headline metrics.

## Codex And Claude Split

Codex is the sole code executor for the repository. Claude may help review
wording, corpus realism, and prompt ideas, but Claude does not own code changes.

## Week 4 Cut Line

Week 4 is the forced scope checkpoint. If real eval, traceability, or failure
analysis are at risk, optional features must be cut before they consume the
remaining evaluation window.

