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

hard_negative_error_rate=1.0 indicates a serious failure mode.

This is a failure finding, not a robustness proof. Retrieval-only
`hybrid_rrf_rerank` had `doc_hit@5=0.05` and `hard_negative_error_rate=1.0`.
The real `final_agentic` hard-negative run also had `grounded_correctness=0.0`,
`doc_hit@5=0.05`, and `hard_negative_error_rate=1.0`. These results must not be
reported as hard-negative robustness.

| split | system | mode | doc_hit@5 | hard_negative_error_rate | interpretation |
| --- | --- | --- | ---: | ---: | --- |
| hard_negative | `hybrid_rrf_rerank` | retrieval_only | 0.0500 | 1.0000 | Retrieval selected the wrong paired evidence in nearly every case; this is a stress-test failure row, not an answer-quality metric. |

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
- hard_negative: 20 cases, used as retrieval/citation robustness pressure.
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
