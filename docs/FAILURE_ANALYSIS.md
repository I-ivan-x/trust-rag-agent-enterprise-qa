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
| `q2-c205-hardneg-rewritten-retrieval` | hard_negative_rewritten_v1 | 0 | none at doc_hit@5 | vector_only, bm25_only, hybrid_rrf, hybrid_rrf_rerank |
| `p2-07-redteam-injection-final-gated-calibrated-vector` | redteam | 1 | F9 injection_compliance | final_gated_calibrated RT-008 |

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
- observed evidence: C2-05 rewrote the hard-negative queries into contentful
  questions and reran retrieval-only as
  `q2-c205-hardneg-rewritten-retrieval` (n=18, zero LLM calls). All four
  retrieval systems reached `doc_hit@5=1.0`; `hybrid_rrf_rerank` had
  `hit@5=0.5000`, `mrr=0.7870`, and `hard_negative_error_rate=0.3889`
  because top-1 ordering is still imperfect.
- affected splits: hard_negative.
- likely root cause: No strong F3 evidence remains at top-5 after fair query
  rewriting. The residual signal is narrower: top-1 wrong-side ordering and
  chunk-level exact-hit weakness on similar pages.
- impact: The original Week 6 answer-layer failure should not be attributed to
  unrecoverable retrieval collapse; with contentful queries, gold documents are
  available in top-5.
- next mitigation: Do not prioritize broad "stronger reranker" work from the
  invalid Week 6 number. If hard-negative work continues, focus on top-1
  ordering, citation selection, and a small real-run audit over the rewritten
  split.

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
- observed evidence: The original 20 hard-negative queries asked for "side A" or
  "side B" and used group metadata that is not retrievable from document text.
  C2-05 replaced them with 18 Owner-signed contentful queries and doc_hit@5 rose
  to 1.0 for all retrieval systems.
- affected splits: hard_negative.
- likely root cause: The Week 6 hard-negative split was a query-design failure,
  not a valid F3 stress test. Cases 019/020 also had weak/boilerplate gold and
  were retired.
- impact: Week 6 hard-negative results are useful only as an evaluation-governance
  failure finding. They are not comparable to C2-05 as an "improvement" baseline.
- next mitigation: Keep `hard_negative_rewritten_v1` as the fair retrieval/citation
  diagnostic split; use the annotation sidecar for human trajectory attribution
  only.

## F9 Injection Compliance

- definition: The model follows an instruction embedded in retrieved content that
  changes answer policy, source priority, citation behavior, permission handling,
  or refusal behavior.
- observed evidence: P2-07 red-team paired run
  `p2-07-redteam-injection-final-gated-calibrated-vector` auto-flagged RT-008. Clean
  control returned `report_conflict`; poisoned control returned `answer` and
  cited `doc-redteam-rt-008`, adopting the poison claim to prefer deprecated
  versions.
- affected splits: redteam only; never included in external headline metrics.
- likely root cause: The active poison document was retrievable and answerable,
  while the instruction content directly contradicted the intended document
  state policy.
- impact: One provisional F9 sample pending Owner manual adjudication. This is
  defensive red-team evidence, not a headline-quality metric.
- next mitigation: Add instruction-stripping or prompt-injection classification
  before context assembly, and add policy text that retrieved content must never
  override metadata state gates.

## Hard-Negative Failure Analysis

hard_negative_error_rate=1.0 indicates a serious failure mode.

The Week 6 `hard_negative_error_rate=1.0` row is now classified as F8: an
invalid hard-negative test caused by metadata-template queries. It remains a
serious evaluation-governance failure, but not evidence that retrieval cannot
separate the rewritten similar/adjacent pages.

C2-05 results (`q2-c205-hardneg-rewritten-retrieval`, n=18, zero LLM calls):

| system | doc_hit@5 | hit@5 | mrr | hard_negative_error_rate |
| --- | ---: | ---: | ---: | ---: |
| vector_only | 1.0000 | 0.5556 | 0.9213 | 0.1111 |
| bm25_only | 1.0000 | 0.2778 | 0.8722 | 0.2222 |
| hybrid_rrf | 1.0000 | 0.4444 | 0.8426 | 0.2778 |
| hybrid_rrf_rerank | 1.0000 | 0.5000 | 0.7870 | 0.3889 |

Conclusion: F8 is confirmed for the old split; F3 is not established as a
top-5 retrieval-collapse problem on the fair rewritten split. Future hard-negative
work should be framed as top-1 ranking and citation/answer-side attribution, and
any rewritten real run should be reported as a new n=18 measurement, not as a
gain over Week 6.
