# Evaluation Report

> Pre-Week-6 obfuscated/agentic smoke results generated before the
> expected_rewrite isolation fix are invalidated and must not be cited.

Mock runs are smoke checks only. Headline metrics require full split scope,
non-mock retrieval where applicable, and a real LLM provider for final/direct
systems. `expected_rewrite` is informational only and is never used for
retrieval, rewrite, or scoring.

## Week 6 Full-Run Inventory

| run_id | split | systems | mode | cases | headline_scope | headline_eligible | mock_used |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| `week6-real-external-full` | external | `direct_llm,final_gated,final_agentic` | real_run | 50/50 | full_split | true | false |
| `week6-real-obfuscated-full` | obfuscated | `final_gated,final_agentic` | real_run | 15/15 | full_split | true | false |
| `week6-hard-negative-real-retrieval` | hard_negative | `hybrid_rrf_rerank` | retrieval_only | 20/20 | full_split | true | false |
| `week6-hard-negative-final-agentic-real` | hard_negative | `final_agentic` | real_run | 20/20 | full_split | true | false |
| `week6-external-retrieval-ablation` | external | `vector_only,bm25_only,hybrid_rrf,hybrid_rrf_rerank` | retrieval_only | 50/50 | full_split | true | false |
| `week6-fixture-functional-regression` | fixture | `final_gated,final_agentic` | mock_smoke | 36/36 | smoke | false | true |
| `q2-c205-hardneg-rewritten-retrieval` | hard_negative | `vector_only,bm25_only,hybrid_rrf,hybrid_rrf_rerank` | retrieval_only | 18/18 | full_split | true | false |

The public corpus index was rebuilt before external retrieval ablation:
40 documents, 442 chunks, `chunks_path=data/generated/public/chunks.jsonl`,
`vector_count=442`, and `keyword_count=442`. A CORS search preview ranked the
public FastAPI CORS document first.

## External End-to-End Metrics

| system | grounded_correctness | raw_correctness | doc_hit@5 | mrr | refusal_rate | false_refusal_rate | false_answer_rate | citation_valid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| direct_llm | 0.0000 | 0.2000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2800 | 0.2800 |
| final_gated | 0.2400 | 0.2400 | 0.7600 | 0.6130 | 0.7400 | 0.4600 | 0.0000 | 1.0000 |
| final_agentic | 0.2400 | 0.2400 | 0.7600 | 0.6130 | 0.7400 | 0.4600 | 0.0000 | 1.0000 |

`grounded_correctness` is the headline metric. `raw_correctness` is reported
only for contamination and parametric-memory analysis.

## Retrieval Tier Ablation

Retrieval-tier metrics measure whether gold evidence is retrieved, not whether
the final answer is correct. `doc_hit@5` and `gold_doc_recall@5` must not be
reported as answer accuracy.

External retrieval-only ablation run: `week6-external-retrieval-ablation`.
It made zero LLM calls, used the real public-corpus retrieval stack, and reports
`mock_used=false`, `toy_retrieval=false`, and `expected_rewrite_used=false`.

| system | hit@1 | hit@3 | hit@5 | doc_hit@1 | doc_hit@3 | doc_hit@5 | gold_doc_recall@1 | gold_doc_recall@3 | gold_doc_recall@5 | mrr | deprecated_confusion_rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vector_only | 0.0800 | 0.1200 | 0.1200 | 0.4400 | 0.5600 | 0.6000 | 0.4100 | 0.5500 | 0.5900 | 0.4967 | 0.2200 |
| bm25_only | 0.1000 | 0.2200 | 0.2800 | 0.5400 | 0.7600 | 0.8000 | 0.5000 | 0.7300 | 0.7700 | 0.6547 | 0.2200 |
| hybrid_rrf | 0.0400 | 0.1800 | 0.2800 | 0.5400 | 0.7600 | 0.8000 | 0.5000 | 0.7400 | 0.7900 | 0.6400 | 0.2000 |
| hybrid_rrf_rerank | 0.0200 | 0.1400 | 0.1800 | 0.5200 | 0.6600 | 0.7800 | 0.4800 | 0.6400 | 0.7600 | 0.6113 | 0.2800 |

This ablation does not prove rerank improvement. On this external split,
`hybrid_rrf_rerank` underperformed `hybrid_rrf` on `hit@5`, `doc_hit@5`,
`gold_doc_recall@5`, and MRR. `bm25_only` and `hybrid_rrf` were the strongest
retrieval tiers by `doc_hit@5`; `hybrid_rrf` had the highest `gold_doc_recall@5`.

## Memorization & Contamination Analysis

The public corpus is drawn from public FastAPI documentation. It may appear in
the DeepSeek training distribution or in related web-scale pretraining data.
Therefore, raw answers can reflect parametric memory rather than retrieved
evidence.

`direct_llm` reached `raw_correctness=0.20` on external cases, showing that the
model can answer some content without retrieval. However, `direct_llm` has no
retrieved citations, so its `grounded_correctness=0.00`. This is the expected
interpretation: raw correctness is a contamination or parametric-leakage signal,
not a final system score.

The raw-vs-grounded gap is used only to analyze memorization risk. It must not
be quoted as headline quality, and raw correctness must not be presented as
TrustRAG Enterprise QA accuracy.

## False Refusal vs False Answer Trade-off

The current system is conservative. On the external full run, both `final_gated`
and `final_agentic` had `false_answer_rate=0.00`, but also
`false_refusal_rate=0.46` and `refusal_rate=0.74`. Low false-answer tendency is
not sufficient evidence of high quality when many answerable queries are refused.

Permission, deprecated-state, evidence, and conflict gates improve safety by
failing closed when evidence is restricted, stale, conflicting, or insufficient.
The measured cost is reduced coverage and lower grounded correctness through
over-refusal. The Week 6 trade-off conclusion is that the system currently
leans toward "fail closed". The next improvement should be gate calibration and
retrieval quality, not relaxing citation or grounding constraints.

## Agentic Result Statement

final_agentic did not outperform final_gated in the Week 6 full run.

The agentic path is wired and audited, and `expected_rewrite_used=false`. In the
obfuscated full run, one rewrite LLM call occurred, but no actual rewritten query
was accepted and the final metrics tied: `final_gated grounded_correctness=0.3333`
and `final_agentic grounded_correctness=0.3333`. This run does not demonstrate
agentic recovery benefit. Do not claim that agentic improves performance.

## Hard Negative Result Statement

The Week 6 hard_negative numbers (`doc_hit@5=0.05`,
`hard_negative_error_rate=1.0`) are retained as an invalid-test finding: the
original 20 queries were metadata templates such as "answer from side A/B" and
contained no retrievable content. They must not be used as robustness evidence
or as a baseline for improvement claims.

C2-05 replaced the queries with Owner-signed contentful questions, retired
cases 019/020, and reran retrieval only as `q2-c205-hardneg-rewritten-retrieval`
(n=18, zero LLM calls, real sentence-transformer embeddings, BGE reranker
available). This is the first valid hard-negative retrieval measurement.

| split | system | mode | n | doc_hit@5 | hit@5 | mrr | hard_negative_error_rate | interpretation |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| hard_negative_rewritten_v1 | `vector_only` | retrieval_only | 18 | 1.0000 | 0.5556 | 0.9213 | 0.1111 | Gold document reaches top-5 for every case; residual error is top-1 wrong-side ranking. |
| hard_negative_rewritten_v1 | `bm25_only` | retrieval_only | 18 | 1.0000 | 0.2778 | 0.8722 | 0.2222 | Gold document reaches top-5 for every case; chunk-level exact hit remains harder. |
| hard_negative_rewritten_v1 | `hybrid_rrf` | retrieval_only | 18 | 1.0000 | 0.4444 | 0.8426 | 0.2778 | Hybrid retrieval finds the gold document in top-5 across the rewritten split. |
| hard_negative_rewritten_v1 | `hybrid_rrf_rerank` | retrieval_only | 18 | 1.0000 | 0.5000 | 0.7870 | 0.3889 | Rerank does not improve top-1 ordering here, but the gold document is still in top-5 for every case. |

Interpretation: the rewritten split confirms F8 for the Week 6 failure. The
original hard-negative test was unfair and uninformative for F3. The C2-05 run
does not prove robust retrieval; it only establishes a fair measurement where
the unfair-query artifact is removed.

Two qualifiers keep `doc_hit@5=1.0` from being over-read:

- **Index scope.** The hard_negative split is retrieved against the
  hard-negative corpus only (~37 docs), so "gold document in top-5" is a
  near-trivial ceiling and must not be read as retrieval strength. The
  informative signals are `hard_negative_error_rate` (0.11–0.39: the confusable
  sibling out-ranks the gold side in 11–39% of cases) and chunk-level `hit@5`
  (0.28–0.56). A stronger robustness test would retrieve against the full
  public+hard-negative index; that is an optional follow-up, not done here.
- **Rerank aggravates sibling confusion.** `hard_negative_error_rate` rises
  monotonically from `vector_only` 0.111 to `hybrid_rrf_rerank` 0.389 — the
  reranker makes top-1 sibling ranking worse, consistent with the external-split
  finding that rerank did not help.

So F3 does not appear as a top-5 recall collapse (that was a query artifact),
but a residual ranking-level hard-negative confusion does exist. "Robust" is not
claimed, and the old 0.05 result must not be cited as an improvement baseline.

## Fixture Functional Regression

Fixture regression run: `week6-fixture-functional-regression`. It covered 36/36
fixture cases with `final_gated` and `final_agentic` in `mock_smoke` mode. It
made zero LLM calls, is `headline_eligible=false`, and includes a mock-run note.
Any fixture grounded or correctness-like value from this run is a toy/mock
functional-regression signal only, not real model or retrieval quality.

The fixture run covered the expected response paths: answer (`none` decision
reason), `no_evidence`, `permission_denied`, `deprecated_only`, and
`conflict_detected`. It is functional regression evidence only and must not be
cited as headline evaluation.

## Data Notes

- external: 50 cases, including 25 `real_user_question` cases and 25
  manifest-authored cases.
- obfuscated: 15 cases, used only for `final_gated` vs `final_agentic`.
- hard_negative: 18 rewritten cases (`hard_negative_rewritten_v1`), used as
  retrieval/citation diagnostics. The original 20-case template-query result is
  archived as an invalid-test finding only.
- fixture: 36 cases, used as non-headline functional regression.
- citation audit is rule-based v1 and requires manual review before any human
  citation-support claim.
- external conflict cases use the existing active-active synthetic conflict
  group because the public FastAPI corpus has no native conflict overlay.

------

# Q2 Phase 1 — Gate Calibration (P1-02 .. P1-06)

This section is Q2 work extending the Q1 report. All runs are external split,
`final_gated`, real LLM, 50 cases, `headline_eligible=true` unless noted.

## Threshold Sweep (P1-02, legacy policy)

Run `q2-p1-02-legacy-threshold-sweep-reconciled`, 5 configs over the now-configurable
`EvidenceGateConfig(min_support_count, min_score)`:

| config | min_support | min_score | false_refusal | false_answer | grounded | refusal | note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| default | 1 | none | 0.46 | 0.00 | 0.24 | 0.74 | |
| support2 | 2 | none | 0.46 | 0.00 | 0.24 | 0.74 | identical |
| score0 | 1 | 0.0 | 0.46 | 0.00 | 0.24 | 0.74 | identical |
| support2_score0 | 2 | 0.0 | 0.46 | 0.00 | 0.24 | 0.74 | identical |
| score1 | 1 | 1.0 | 0.72 | 0.00 | 0.22 | 1.00 | degenerate: refuses all, 0 LLM calls, `headline_eligible=false` |

**Finding: the threshold knobs are inert.** Four of five configs are bit-for-bit
identical; only `min_score=1.0` changes anything, and it does so degenerately
(refuses every case, zero answers). Loosening does nothing because retrieved
scores already clear 0; tightening to 1.0 refuses everything. **Over-refusal on
this split is not threshold-driven** — it is policy/neighbor-driven, which is
exactly what failure classes F1/F2 and the hard-negative adjudication predicted.
Evidence-gate thresholds are therefore not the lever; the trust *policy* is.

**Reconciliation note.** The earlier run `q2-p1-02-legacy-threshold-sweep`
reported default metrics of grounded 0.28 / false_refusal 0.34 / refusal 0.62,
but all `final_gated` answer rows in that run carried `Vector retrieval
unavailable: Qdrant ... collection doesn't exist`. That run silently fell back
to keyword-only retrieval and is not comparable to the Week 6 headline. After
rebuilding the Qdrant collection (`vector_count=442`) and rerunning the same
legacy/default configuration, `q2-p1-06-reconciled-legacy-default` and the
corrected sweep exactly match Week 6: grounded 0.24 / false_refusal 0.46 /
refusal 0.74, with zero vector-unavailable warnings. Therefore P1-01 did **not**
make the default gate looser; the apparent 0.28 result was runtime retrieval
stack drift.

## Policy Variant (P1-03/P1-04, neighbor_tolerant)

Run `q2-p1-07-neighbor-tolerant-fixed`. `TRUST_GATE_POLICY=neighbor_tolerant`
ignores restricted/deprecated neighbors when clean active evidence is judged
sufficient, while still refusing when only restricted/deprecated evidence
remains.

| policy | false_refusal | false_answer | grounded | refusal |
| --- | ---: | ---: | ---: | ---: |
| legacy (default) | 0.46 | 0.00 | **0.24** | 0.74 |
| neighbor_tolerant_fixed | 0.44 | 0.00 | 0.22 | 0.72 |

The original `neighbor_tolerant` run (`q2-p1-04-neighbor-tolerant-default`) is
invalid for baseline use: it ran with vector retrieval unavailable and leaked
permission/no-evidence cases (false_answer 0.22). P1-07 fixes the permission
leak by keeping ACL fail-closed whenever restricted chunks match the query; the
fixed run has false_answer 0.00. It still does not beat legacy/default:
false_refusal only moves 0.46 → 0.44 and grounded drops 0.24 → 0.22. It should
not enter any baseline.

## Cost-Asymmetry Conclusion

In enterprise QA, a confident wrong answer about permissions or coverage is an
incident; a refusal is an inconvenience. The fixed neighbor_tolerant policy buys
only a 0.02 drop in false-refusal and loses grounded correctness. Under the
project's stated cost asymmetry, that is not a useful trade.

The deeper conclusion sets up Q2 Phase 3: a *blanket* policy switch is too
coarse. Releasing false-refusal **safely** requires per-case, evidence-quality
decisions that re-fetch clean evidence rather than tolerating dirty neighbors —
i.e. the typed-action agent's metadata-filtered re-retrieval (action b), which
can lift coverage on genuinely answerable cases without answering
permission-restricted ones. P1-05's negative result is the motivation for that
design, and it also fixes a guardrail: any future false-refusal release must be
checked against permission/no-evidence leakage, not just against the aggregate
refusal rate.

## P1-06 — Baseline Freeze

Frozen `final_gated_calibrated` = **legacy policy, default config**
(`min_support_count=1`, `min_score=none`; reference run
`q2-p1-02-legacy-threshold-sweep-reconciled/default`; cross-check run
`q2-p1-06-reconciled-legacy-default`): false_refusal 0.46, false_answer 0.00,
grounded 0.24, refusal 0.74, citation_valid 1.00. This is not claimed as an
improvement over Week 6; it is the same fail-closed baseline made explicit and
reproducible after the retrieval-stack drift was fixed. No threshold or policy
variant measured in Phase 1 improves grounded correctness without violating the
false-answer constraint, so `final_gated_calibrated` freezes the conservative
legacy/default point for Q2 comparisons.

---

## Q2 Phase 3 P3-09/P3-10 Agent Ablation

- run_id: `p3-09-agent-ablation`
- run_dir: `data/eval_runs/p3-09-agent-ablation`
- systems: `final_gated_calibrated, final_agentic_v2_rule, final_agentic_v2_llm`
- cases: `22` unique x `k=3`
- mode: `real_run`
- headline_eligible: `False`
- headline_scope: `agent_phase3_diagnostic`
- mock_used: `False`
- toy_retrieval: `False`
- expected_rewrite_used: `False`
- vector_unavailable: `False`
- llm_call_count: `42` (answer `24`, controller `18`, rewrite `0`)
- llm_usage_total_tokens: `79194`

> Diagnostic-only P3 agent ablation. agent_residual/AR cases and this mixed testbed never enter external headline metrics.

### Metric Boundary Carry-Forward

Retrieval-tier metrics measure whether gold evidence is retrieved, not whether the final answer is correct.

Week 6 boundary retained: final_agentic did not outperform final_gated; P3 agent deltas are diagnostic small-n observations, not headline claims.

### Testbed

| slice | count / ids |
| --- | --- |
| obfuscated | 15 cases |
| external false-refusal controls | external-003, external-004, external-010, external-014, external-015, external-017 |
| legal-trigger | obfuscated-015, AR-002 |
| hard-negative | excluded |

### Grounded And Reliability

| system | grounded | pass^1 attempt mean | pass^3 | action sequence consistency |
| --- | ---: | ---: | ---: | ---: |
| final_gated_calibrated | 0.2273 | 0.2273 | 0.2273 | 1.0000 |
| final_agentic_v2_rule | 0.2727 | 0.2727 | 0.2727 | 1.0000 |
| final_agentic_v2_llm | 0.2727 | 0.2727 | 0.2727 | 1.0000 |

### LLM Calls

| system | answer | controller | rewrite | total |
| --- | ---: | ---: | ---: | ---: |
| final_gated_calibrated | 6 | 0 | 0 | 6 |
| final_agentic_v2_rule | 9 | 0 | 0 | 9 |
| final_agentic_v2_llm | 9 | 18 | 0 | 27 |

### Agent Attribution

| action | trigger | accept | success | false_recovery_count | ineffective |
| --- | ---: | ---: | ---: | ---: | ---: |
| rewrite_query | 18 | 12 | 6 | 0 | 6 |
| filtered_retrieval | 0 | 0 | 0 | 0 | 0 |
| present_conflict_set | 0 | 0 | 0 | 0 | 0 |
| refuse_with_explanation | 36 | 18 | 0 | 0 | 0 |

LLM controller:

- llm_propose_count: `18`
- llm_accept_count: `10`
- llm_fallback_count: `8`
- llm_fallback_rate: `0.4444444444444444`

Per-system action attribution:

| system | action | trigger | accept | success | false_recovery_count | ineffective |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| final_agentic_v2_rule | rewrite_query | 9 | 6 | 3 | 0 | 3 |
| final_agentic_v2_rule | filtered_retrieval | 0 | 0 | 0 | 0 | 0 |
| final_agentic_v2_rule | present_conflict_set | 0 | 0 | 0 | 0 | 0 |
| final_agentic_v2_rule | refuse_with_explanation | 18 | 9 | 0 | 0 | 0 |
| final_agentic_v2_llm | rewrite_query | 9 | 6 | 3 | 0 | 3 |
| final_agentic_v2_llm | filtered_retrieval | 0 | 0 | 0 | 0 | 0 |
| final_agentic_v2_llm | present_conflict_set | 0 | 0 | 0 | 0 | 0 |
| final_agentic_v2_llm | refuse_with_explanation | 18 | 9 | 0 | 0 | 0 |

### Diagnostic Anchor

P3-09 zero-token precheck: 33 cases; failure distribution `{'NO_RECOVERY': 29, 'PERMISSION_BLOCKED': 2, 'WEAK_RECALL': 2}`; a legal trigger=2, b legal trigger=0, b gold-doc-recoverable=0, d legal trigger=0.

### P3-11 Interpretation

Phenomenon: action b/d have no legal trigger and action-a recovery is confined to the legal-trigger diagnostic corner. The small observed delta is not a headline gain.

Root cause: the remaining false-refusals are policy-adjudication style failures (F1/F2), not retrieval recoveries. Action b has a broad diagnostic surface, but gold-doc-recoverable remains 0, and filtered retrieval does not bypass ACL/state gates.

Next step: treat the mechanism as usable and guarded, while recording that the current frozen testbed has no broad measurable agent gain. The dual-controller ablation has degraded to a vs e on n=2 legal-trigger cases, so it is qualitative and statistically powerless.

