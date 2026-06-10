# Schema Review Checklist

## DocumentMetadata

- `doc_id`, `title`, and `allowed_roles` are not empty.
- Document type, status, access level, corpus source, source origin, and
  metadata origin use shared enums.
- Supersession, conflict group, hard negative group, and authoritative flags
  are available.
- `language` matches the document body language.

## Chunk

- Chunk IDs are stable and include document linkage.
- Access, status, tags, corpus, origin, hard negative, conflict, and authority
  fields are preserved from document metadata.
- Token and character counts are present for later chunking checks.
- Week 1 chunks must not include YAML front matter text.
- Week 1 chunk indexes must be continuous per document starting at 0.

## Ingestion

- Loader ignores hidden, temporary, empty, cache, `.git`, and `.venv` files.
- `RawDocument.source_path` is stable and relative.
- Markdown parser ignores headings inside fenced code blocks.
- TXT parser uses a metadata fallback that still validates as `DocumentMetadata`.
- Generated JSONL files validate against the Week 0 schemas.

## Citation

- Citation IDs, document IDs, chunk IDs, section paths, and locators are present.
- Support type and verification status use shared enums.

## ChatRequest And ChatResponse

- User scope (role, department, clearance) and retrieval options are part of the
  request.
- Response carries citations, decision, trace ID, and optional retrieved chunk
  previews.
- `response_mode` is limited to exactly: `answer`, `refuse_no_evidence`,
  `refuse_permission`, `warn_deprecated`, `report_conflict`, `system_error`.
- `ask_clarification` must not appear as a supported Q1 response mode.

## Conflict Detection

- `report_conflict` fires only when surviving post-gate evidence has >= 2
  distinct `doc_id` sharing the same `conflict_group_id` with both
  `status == active`.
- Active vs deprecated in the same group routes to `warn_deprecated`, not
  conflict.
- Decision priority is enforced:
  `refuse_permission > report_conflict > warn_deprecated > answer/refuse_no_evidence`.

## TraceRecord

- Stores query, user, workflow version, steps, retrieval trace, gates,
  decision, usage, latency, and agentic recovery details.
- Agentic recovery stores original query, rewritten query, evidence sufficiency
  flags, and max rewrite rounds.

## EvalCase

- Eval split, corpus source, query source, query style, title overlap score,
  and real-model requirement are explicit.
- `gold_chunk_ids` may be empty in Week 0 and are backfilled for demo fixture
  cases in Week 1.
- `expected_rewrite` is informational and not a scoring target.

## JSON Round-Trip

- Every schema used in tests serializes with `model_dump_json()` and reloads
  with `model_validate_json()`.

## Enum Consistency

- Shared enums are the only source for document state, corpus, eval, query,
  retrieval, citation, and decision values.

## Mock Boundary

- Mock embeddings and mock LLM output are valid for tests, CI, and smoke only.
- Mock output must not appear in formal evaluation reports or headline metrics.
