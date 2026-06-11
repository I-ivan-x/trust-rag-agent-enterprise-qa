# Prompt Design Review

Week 3 introduces the first online answer-generation prompt for the local
`/chat` path. This is a working design note, not a final evaluation report.

## Week 3 Prompt Goals

- Convert a user query and assembled context into a structured answer.
- Require the model to answer only from the provided context.
- Require JSON-only output with `answer_text`, `claims`, `response_mode`, and
  `warnings`.
- Require every claim to carry `supporting_chunk_ids` copied exactly from the
  provided context.
- Keep citation binding deterministic after generation.

## Grounding Rules

The prompt explicitly states that the model must not use outside knowledge. If
no context is available, the Week 3 generator returns a no-evidence style answer
without invoking the full Week 4 refusal controller.

The parser rejects supporting chunk IDs that are not present in the
`ContextPack`, so a model cannot create citation IDs or chunk IDs that were not
retrieved and assembled.

## Mock LLM Boundary

`MockLLMClient` is deterministic and exists only for tests, local demo, and
smoke runs. Its output must not be used for formal end-to-end metrics or
headline claims.

Real LLM generation is represented by an OpenAI-compatible client interface, but
Week 3 does not make real LLM calls by default and does not use a real LLM for
formal evaluation.

## Parser Fallback

If model output is not valid JSON, the parser falls back deterministically to the
first assembled context chunk and emits a warning. This keeps local smoke tests
stable while making parser failure visible.

## Known Limitations

- Citation verifier v1 is not implemented in Week 3.
- ACL, document state, and evidence gates are not connected in Week 3.
- The no-evidence path is lightweight and should not be confused with the Week 4
  refusal controller.
- Agentic query rewrite, second-pass retrieval, and recovery are not connected.
- Prompt quality has not been measured against public external formal eval.

## Review Ownership

Claude can review prompt design and point out grounding risks. Codex owns the
final prompt, parser, tests, and code changes in this repository.
