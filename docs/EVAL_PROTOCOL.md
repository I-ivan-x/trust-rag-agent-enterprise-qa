# Eval Protocol

Evaluation exists to prove grounded trustworthiness, not to produce one
unqualified accuracy number.

## Splits

- `fixture`: synthetic Week 0 data for schema and smoke checks.
- `external`: public external documents for headline evaluation.
- `hard_negative`: adversarial near-miss documents.
- `obfuscated`: rewritten queries that test robustness without changing gold
  evidence.

## Metrics

`grounded_correctness` is the headline metric. It requires the answer to be
correct and supported by retrieved/cited evidence.

`raw_correctness` records whether the answer text is correct even when grounding
is missing or weak.

`parametric_leakage_gap` tracks the difference between raw correctness and
grounded correctness. A large gap is a warning sign that the system may be
answering from model prior knowledge instead of evidence.

## Query Source

Eval cases record `query_source` so the project can distinguish real user
questions, manifest-authored questions, and manual adversarial questions. At
least 50% of formal Q1 user-facing questions should come from real user-style
questions rather than only author-written fixtures.

## Leakage Check

`check_eval_leakage.py` is reserved for later weeks. It should backfill
`title_overlap_score` and flag cases where the query gives away the document
title or answer too directly.

## Agentic Rewrite

`expected_rewrite` is informational only. It can help inspect agentic recovery
behavior, but it must not be counted as a scoring target.

## Headline Rule

Headline claims must use grounded correctness and must come from real embedding,
real reranker, and real LLM paths. Mock eval runs are allowed only for smoke
testing.

