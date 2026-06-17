# Eval Protocol

Evaluation exists to prove grounded trustworthiness, not to produce one
unqualified accuracy number.

## Splits (frozen sizes)

| Split | Count | Use |
| ----- | ----- | --- |
| fixture | 36 | functional regression; never headline |
| external | 50 | headline primary basis |
| hard_negative | 18 | retrieval/citation diagnostics (`hard_negative_rewritten_v1`) |
| obfuscated | 15 | agentic loop value |

Week 0 ships only 5 placeholder fixture cases in
`data/gold_eval/demo_eval.jsonl`; `gold_chunk_ids` are empty until Week 1.

## Headline Metric

`grounded_correctness` is the only headline answer metric: the answer is
correct **and** every citation comes from the ContextPack (citation_validity)
**and** at least one citation is judged to support the core claim.

`raw_correctness` (answer text correct, ignoring citations) is reference only.
`parametric_leakage_gap = raw_correctness - grounded_correctness` flags
answering from model prior knowledge instead of evidence.

## Eval Author / Corpus Author Isolation

To avoid corpus-and-eval collusion:

1. The corpus and its manifest are frozen first.
2. The eval author does not read full text - only manifest, title, doc_type,
   tags, section titles, status, access level, source URL, and metadata origin.
3. Queries and `expected_behavior` are written from the manifest.
4. Codex backfills `gold_chunk_ids` from real chunks; the Owner spot-checks.
5. `check_eval_leakage.py` runs before the data is frozen; the report is
   archived. Cases that fail are rewritten or downgraded to an `easy` label.

## Query Source

Each case records `query_source` (`real_user_question` or `manifest_authored`).
For the external split, at least 50% of queries must be real human questions
(with `query_source_url`), reworded/anonymized but keeping the original
phrasing style, so the set is not saturated by title-word matching.

## Leakage Check

`check_eval_leakage.py` backfills `title_overlap_score` and enforces a
two-sided boundary: title overlap > 0.6 -> flag; query content must overlap the
gold content set so metadata-only questions are rejected; answer-sentence copy
(char similarity > 0.8) -> reject; external split must have >= 40% of queries
with `title_overlap_score < 0.3`. For hard_negative, high title overlap is
diagnostic but non-blocking because similar-title pairs intentionally share
title vocabulary.

## Agentic Rewrite

`expected_rewrite` is informational and is never scored. Rewrite statistics
(trigger/success/second-pass) are reported as observability only. The value of
the agentic loop is proven solely by **final_gated vs final_agentic on the
obfuscated split** (grounded_correctness / correct refusal).

## Headline Rule

Headline claims use grounded_correctness from real embedding + real reranker +
real LLM paths. Mock runs are valid for smoke tests only, never for reports.

The public external split is a headline source only when evaluated with real
providers. Synthetic fixtures remain functional regression only. Hard negative
results are reported as a separate retrieval/citation robustness slice, not
merged into the headline external score.

## Regression Gates

Frozen eval baselines live in `data/eval_baselines/regression_baseline_v1.json`.
Each gated metric records `source_run_id`, direction, and tolerance. The checker
is `scripts/check_eval_regression.py`; it only reads existing `summary.json`
files and never reruns eval or calls an LLM.

There are two layers:

1. CI layer: zero-token pytest coverage verifies checker behavior and
   headline-eligibility invariants. Mock or synthetic summaries can test the
   contract, but must not be reported as real metric validation.
2. Manual/offline layer: after a new real or formal retrieval run is produced,
   run the checker against its `summary.json`. This may require token spend to
   create the new real run, so it is not part of CI. Any gated metric outside
   tolerance fails the manual gate.

Week 5A prepares corpus artifacts only. It does not implement `run_eval.py`,
metrics summaries, formal real-LLM runs, or an `EVALUATION_REPORT`.

For Week 5A hard negatives, eval authors should treat `pair_type` as a
conservative corpus-construction label. Current public-derived pairs are
`adjacent_topic` or `similar_title`; unsupported labels such as
`deprecated_vs_active` or `official_doc_vs_meeting_note` must not be inferred
from these pairs.
