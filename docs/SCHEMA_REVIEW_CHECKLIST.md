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

## Retrieval Indexes

- Embedding providers expose `embed_texts()` and `embed_query()`.
- Mock embeddings are deterministic and marked smoke-test only.
- SentenceTransformer embeddings are the formal retrieval-eval direction.
- Qdrant payloads preserve chunk metadata needed for later gates.
- Whoosh fields include chunk/document IDs, text, section path text, status,
  access level, and corpus source.
- Metadata filters support status, access level, corpus source, and doc ID.

## Hybrid Retrieval

- RRF uses `sum(1 / (k + rank_i))`.
- Fused results deduplicate by `chunk_id`.
- `vector_score`, `keyword_score`, and `rrf_score` are preserved where
  available.
- Hybrid rank starts at 1 after fusion.
- Week 2 does not include reranker logic or rerank-improvement reporting.

## Rerank And Context

- Reranked chunks preserve original vector, keyword, and RRF scores.
- `rerank_score` is present after reranking.
- Context assembly deduplicates by `chunk_id`.
- Context assembly preserves status, access level, allowed roles, corpus source,
  metadata origin, line range, section path, and scores.
- Restricted or deprecated metadata is preserved in Week 3 but not gated until
  Week 4.

## Citation

- Citation IDs, document IDs, chunk IDs, section paths, and locators are present.
- Support type and verification status use shared enums.
- Week 3 citation binding starts with `verification_status=unchecked`; citation
  verifier v1 is not implemented yet.

## ChatRequest And ChatResponse

- User scope (role, department, clearance) and retrieval options are part of the
  request.
- Week 3 also accepts the flat demo request shape with `user_role`,
  `user_department`, `user_clearance`, and `retrieval_options`.
- Response carries citations, decision, trace ID, and optional retrieved chunk
  previews.
- Response carries top-level `response_mode`, provider metadata, and warnings
  for mock/provider boundaries where applicable.
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

- Mock embeddings, mock reranker output, and mock LLM output are valid for tests,
  CI, local demo, and smoke only.
- Mock output must not appear in formal evaluation reports or headline metrics.
