# Failure Analysis

This report summarizes Week 6 full real-run and closeout artifacts. It is a
failure taxonomy, not a single latest-run dump.

## Run-Level Failure Counts

| run_id | split | failures | dominant reason | systems |
| --- | --- | ---: | --- | --- |
| `week6-real-external-full` | external | 126 | grounded_correctness_false | direct_llm 50, final_gated 38, final_agentic 38 |
| `week6-real-obfuscated-full` | obfuscated | 20 | grounded_correctness_false | final_gated 10, final_agentic 10 |
| `week6-hard-negative-real-retrieval` | hard_negative | 19 | gold_doc_not_retrieved | hybrid_rrf_rerank 19 |
| `week6-hard-negative-final-agentic-real` | hard_negative | 20 | grounded_correctness_false | final_agentic 20 |
| `week6-fixture-functional-regression` | fixture | 10 | grounded_correctness_false | final_gated 5, final_agentic 5 |

## F1 Over-Refusal / Conservative Gate Failure

- definition: The system refuses an answerable query because gates judge the
  retrieved evidence as insufficient, restricted, deprecated, or conflicting.
- observed evidence: External `final_gated` and `final_agentic` each refused
  37/50 cases, with `false_refusal_rate=0.46`. Obfuscated final systems refused
  13/15 cases, with `false_refusal_rate=0.60`.
- affected splits: external, obfuscated.
- likely root cause: Trust gates fail closed when retrieval surfaces restricted,
  deprecated, or conflicting neighbors near answerable public docs.
- impact: Low false-answer tendency but reduced coverage and lower
  grounded_correctness.
- next mitigation: Calibrate evidence thresholds, state-gate handling, and
  conflict/deprecated policies without relaxing citation requirements.

## F2 Permission or Deprecated Gate Dominates Answerability

- definition: Permission or document-state gates suppress an answer even when
  relevant evidence may exist elsewhere in the retrieved set.
- observed evidence: External final systems show `deprecated_confusion_rate=0.26`;
  obfuscated final systems show `deprecated_confusion_rate=0.40`.
- affected splits: external, obfuscated.
- likely root cause: Retrieved neighbors include restricted or deprecated chunks,
  and the policy layer treats those as blocking signals before enough clean
  evidence is selected.
- impact: Safety posture improves, but answerable queries can become false
  refusals.
- next mitigation: Add metadata-aware ranking, cleaner evidence selection, and
  policy calibration that distinguishes "deprecated neighbor present" from
  "only deprecated evidence available".

## F3 Hard-Negative Retrieval Confusion

- definition: Retrieval ranks a confusing adjacent or similar-title document
  above the gold side of the hard-negative pair.
- observed evidence: `hybrid_rrf_rerank` on hard_negative had `doc_hit@5=0.05`
  and `hard_negative_error_rate=1.0`. The real `final_agentic` hard-negative run
  also had `doc_hit@5=0.05`, `grounded_correctness=0.0`, and
  `hard_negative_error_rate=1.0`.
- affected splits: hard_negative.
- likely root cause: Query wording such as "answer from side A/B" is not enough
  for semantic retrieval/reranking to identify the intended pair side; ranking
  collapses toward globally similar later pairs.
- impact: The answer layer cannot recover because target evidence usually does
  not reach the top retrieved set.
- next mitigation: Stronger reranker, metadata-aware rerank, pair/group-aware
  retrieval features, version-aware ranking, and hard-negative-specific
  calibration.

## F4 Citation Support Insufficient Despite Retrieved Evidence

- definition: The answer has structurally valid citations but the cited evidence
  may not support the intended gold claim or may support the wrong hard-negative
  side.
- observed evidence: The hard-negative `final_agentic` summary reports
  `citation_valid=1.0` but `grounded_correctness=0.0` and
  `hard_negative_error_rate=1.0`.
- affected splits: hard_negative, external, obfuscated.
- likely root cause: Rule-based citation validity checks structure and available
  retrieved support, but cannot replace human judgment about claim-level support.
- impact: Citation structure can look healthy even when retrieval selected the
  wrong evidence.
- next mitigation: Manual citation support audit, claim-level entailment checks,
  and hard-negative citation adjudication.

## F5 Agentic No-Op / Rewrite Not Triggered or Not Useful

- definition: The agentic path is available but does not produce a useful
  second-pass retrieval improvement.
- observed evidence: External final systems tied at `grounded_correctness=0.24`.
  Obfuscated final systems tied at `grounded_correctness=0.3333`. The obfuscated
  run recorded one rewrite LLM call, but no accepted rewritten query and no
  metric improvement.
- affected splits: external, obfuscated, hard_negative.
- likely root cause: The rewrite gate is conservative, and when gates classify
  evidence as permission/deprecated/conflict blocked, rewrite is intentionally
  not used.
- impact: Agentic recovery is implemented but not yet beneficial in measured
  Week 6 full runs.
- next mitigation: Add targeted recovery cases, improve rewrite decision
  criteria, and evaluate second-pass retrieval only where policy gates allow it.

## F6 Parametric Knowledge Not Accepted as Grounded Evidence

- definition: A direct LLM answer may be textually plausible, but without
  retrieved citations it is not accepted as grounded.
- observed evidence: External `direct_llm` had `raw_correctness=0.20` but
  `grounded_correctness=0.00` and `citation_valid=0.28`.
- affected splits: external.
- likely root cause: Public FastAPI content may be memorized by the model, but
  the system requires retrieved, cited evidence.
- impact: Raw correctness can indicate contamination or parametric memory but
  must not be reported as system quality.
- next mitigation: Keep raw-vs-grounded reporting separate and use private or
  held-out corpora for future contamination-resistant evaluation.

## F7 Conflict Policy Suppresses Answer

- definition: Conflict detection blocks answer generation when active retrieved
  evidence disagrees or appears unsafe to merge.
- observed evidence: Fixture regression covered `conflict_detected` with 8
  result rows. External split includes conflict cases, and final systems lean
  toward refusal when conflicting neighbors are retrieved.
- affected splits: fixture, external.
- likely root cause: Conflict policy is intentionally conservative and can be
  triggered by adjacent active-active evidence.
- impact: Reduces false confident answers, but can increase over-refusal.
- next mitigation: Improve conflict grouping, add conflict-aware retrieval, and
  distinguish true active-active conflict from merely adjacent related docs.

## F8 Gold Definition / Evaluation Mismatch Risk

- definition: The gold target or scoring rule may be narrower than what the
  retrieval/answer system can infer from the query wording.
- observed evidence: Hard-negative queries ask for "side A" or "side B" and use
  narrow gold doc IDs. Traces show top retrieved docs often come from different
  hard-negative groups, not the target group.
- affected splits: hard_negative.
- likely root cause: Hard-negative query formulation and pair construction may
  require metadata that is not explicit enough in the query or index.
- impact: Some failures may combine real retrieval weakness with gold design
  difficulty.
- next mitigation: Manual adjudication of hard-negative pairs, clearer query
  wording, and metadata-aware retrieval experiments.

## Hard-Negative Failure Analysis

hard_negative_error_rate=1.0 indicates a serious failure mode.

The evidence supports at least two plausible causes:

1. Retrieval/rerank cannot distinguish similar documents reliably. For example,
   `hard-negative-001` has gold doc `hard-negative-hn-fastapi-0001-a`, but
   `hybrid_rrf_rerank` top docs begin with `hard-negative-hn-fastapi-0019-b`,
   `hard-negative-hn-fastapi-0019-a`, and `hard-negative-hn-fastapi-0020-a`.
   `hard-negative-002` targets `hard-negative-hn-fastapi-0002-b`, but the top
   docs again begin with the 0019/0020 groups. The real `final_agentic` run shows
   the same pattern.
2. The hard-negative gold definition or pair construction may be too narrow.
   The manifest labels pairs as `similar_title` or `adjacent_topic`, and queries
   refer to "side A" or "side B". If the index does not expose that side/group
   metadata to retrieval, the gold target may require information that semantic
   retrieval cannot infer from the natural query alone.

Current evidence is insufficient to fully separate retrieval failure from gold
design issue; but the result is a real stress-test failure and must not be
reported as robustness.

Recommended mitigations:

- stronger reranker;
- metadata-aware rerank;
- version-aware ranking;
- conflict-aware retrieval;
- hard-negative-specific calibration;
- manual adjudication of hard-negative pairs.
