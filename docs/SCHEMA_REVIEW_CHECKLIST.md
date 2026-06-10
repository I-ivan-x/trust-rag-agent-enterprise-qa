# Schema Review Checklist

## DocumentMetadata

- `doc_id`, `title`, and `allowed_roles` are not empty.
- Document type, status, access level, corpus source, source origin, and metadata
  origin use shared enums.
- Supersession, conflict group, hard negative group, and authoritative flags are
  available.

## Chunk

- Chunk IDs are stable and include document linkage.
- Access, status, tags, corpus, origin, hard negative, conflict, and authority
  fields are preserved from document metadata.
- Token and character counts are present for later chunking checks.

## Citation

- Citation IDs, document IDs, chunk IDs, section paths, and locators are present.
- Support type and verification status use shared enums.

## ChatRequest And ChatResponse

- User scope and retrieval options are part of the request.
- Response carries citations, decision, trace ID, and optional retrieved chunk
  previews.
- Response modes are limited to answer, refusal, warning, conflict report, and
  system error states.

## TraceRecord

- Trace record stores query, user, workflow version, steps, retrieval trace,
  gates, decision, usage, latency, and agentic recovery details.
- Agentic recovery stores original query, rewritten query, evidence sufficiency
  flags, and max rewrite rounds.

## EvalCase

- Eval split, corpus source, query source, query style, title overlap score, and
  real-model requirement are explicit.
- Gold chunk IDs may be empty in Week 0.
- `expected_rewrite` is informational and not a scoring target.

## JSON Round-Trip

- Every schema used in tests must serialize with `model_dump_json()` and reload
  with `model_validate_json()`.

## Enum Consistency

- Shared enums are the only source for document state, corpus, eval, query,
  retrieval, citation, and decision values.

## Disallowed Clarification Mode

- `ask_clarification` must not appear as a supported Q1 response mode.

## Mock Boundary

- Mock embeddings and mock LLM output are valid for tests, CI, and smoke tests
  only.
- Mock output must not be used in formal evaluation reports or headline metrics.

