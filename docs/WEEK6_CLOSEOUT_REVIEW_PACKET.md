# Week 6 Closeout Review Packet

Project: TrustRAG Enterprise QA

Scope: Week 6 evaluation closeout only. This packet does not include Week 7/8
deployment, demo polish, slides, resume wording, Docker, or Streamlit work.

## 1. Week 6 Full-Run Run Inventory

| run_id | split | systems | mode | cases | headline_eligible |
| --- | --- | --- | --- | ---: | --- |
| `week6-real-external-full` | external | `direct_llm,final_gated,final_agentic` | real_run | 50/50 | true |
| `week6-real-obfuscated-full` | obfuscated | `final_gated,final_agentic` | real_run | 15/15 | true |
| `week6-hard-negative-real-retrieval` | hard_negative | `hybrid_rrf_rerank` | retrieval_only | 20/20 | true |
| `week6-hard-negative-final-agentic-real` | hard_negative | `final_agentic` | real_run | 20/20 | true |
| `week6-external-retrieval-ablation` | external | `vector_only,bm25_only,hybrid_rrf,hybrid_rrf_rerank` | retrieval_only | 50/50 | true |
| `week6-fixture-functional-regression` | fixture | `final_gated,final_agentic` | mock_smoke | 36/36 | false |

All real/full evaluation artifacts are under `data/eval_runs/`. The run artifact
directory is gitignored, so reviewers should regenerate if they need local files
in a fresh clone.

## 2. External End-to-End Metrics

| system | grounded_correctness | raw_correctness | doc_hit@5 | mrr | refusal_rate | false_refusal_rate | false_answer_rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| direct_llm | 0.0000 | 0.2000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2800 |
| final_gated | 0.2400 | 0.2400 | 0.7600 | 0.6130 | 0.7400 | 0.4600 | 0.0000 |
| final_agentic | 0.2400 | 0.2400 | 0.7600 | 0.6130 | 0.7400 | 0.4600 | 0.0000 |

Headline metric: grounded correctness. Raw correctness is contamination and
parametric-memory context only.

## 3. External Retrieval-Tier Ablation

Run: `week6-external-retrieval-ablation`. It used public corpus index with 442
chunks and made zero LLM calls.

| system | hit@1 | hit@3 | hit@5 | doc_hit@1 | doc_hit@3 | doc_hit@5 | gold_doc_recall@5 | mrr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vector_only | 0.0800 | 0.1200 | 0.1200 | 0.4400 | 0.5600 | 0.6000 | 0.5900 | 0.4967 |
| bm25_only | 0.1000 | 0.2200 | 0.2800 | 0.5400 | 0.7600 | 0.8000 | 0.7700 | 0.6547 |
| hybrid_rrf | 0.0400 | 0.1800 | 0.2800 | 0.5400 | 0.7600 | 0.8000 | 0.7900 | 0.6400 |
| hybrid_rrf_rerank | 0.0200 | 0.1400 | 0.1800 | 0.5200 | 0.6600 | 0.7800 | 0.7600 | 0.6113 |

Retrieval-tier metrics measure whether gold evidence is retrieved, not whether
the final answer is correct. This ablation does not prove rerank improvement.

## 4. Obfuscated Final Gated vs Final Agentic

| system | grounded_correctness | raw_correctness | doc_hit@5 | mrr | refusal_rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| final_gated | 0.3333 | 0.3333 | 0.8667 | 0.7356 | 0.8667 |
| final_agentic | 0.3333 | 0.3333 | 0.8667 | 0.7356 | 0.8667 |

Agentic delta: 0. `final_agentic` did not outperform `final_gated` in the Week
6 full run.

## 5. Hard Negative Results

| system | mode | grounded_correctness | doc_hit@5 | mrr | hard_negative_error_rate |
| --- | --- | ---: | ---: | ---: | ---: |
| hybrid_rrf_rerank | retrieval_only | n/a | 0.0500 | 0.0250 | 1.0000 |
| final_agentic | real_run | 0.0000 | 0.0500 | 0.0250 | 1.0000 |

`hard_negative_error_rate=1.0` is a failure finding, not a robustness result.

## 6. Fixture Functional Regression

Run: `week6-fixture-functional-regression`. It covered 36/36 fixture cases in
mock smoke mode, made zero LLM calls, and is not headline eligible.

Response-mode coverage:

- answer path: decision reason `none`;
- no evidence: `no_evidence`;
- permission gate: `permission_denied`;
- deprecated state gate: `deprecated_only`;
- conflict policy: `conflict_detected`.

## 7. Contamination / Raw-vs-Grounded Interpretation

The public corpus uses public FastAPI documentation, which may be memorized by
the real LLM. Direct LLM raw correctness can therefore reflect parametric memory.
The external `direct_llm` baseline had `raw_correctness=0.20` but
`grounded_correctness=0.00`, because it had no retrieved evidence or verifiable
citations. Raw-vs-grounded gap is contamination analysis, not system quality.

## 8. False Refusal / False Answer Trade-off

Final systems show low false-answer rates but high false-refusal rates. The
system currently fails closed: safer against unsupported answers, but with lower
coverage. Future work should calibrate gates and retrieval, not remove grounding
or citation constraints.

## 9. Failure Taxonomy Summary

- F1 Over-refusal / conservative gate failure.
- F2 Permission or deprecated gate dominates answerability.
- F3 Hard-negative retrieval confusion.
- F4 Citation support insufficient despite retrieved evidence.
- F5 Agentic no-op / rewrite not triggered or not useful.
- F6 Parametric knowledge not accepted as grounded evidence.
- F7 Conflict policy suppresses answer.
- F8 Gold definition / evaluation mismatch risk.

See `docs/FAILURE_ANALYSIS.md` for definitions, evidence, affected splits,
likely causes, impact, and mitigation.

## 10. Citation Audit Status

Current citation audit is rule-based v1, not human adjudication. It supports
structural citation checks only. Q1 closeout still needs at least 25 manual
citation-support examples, ideally 40, plus a one-week-later re-label pass for
self-consistency.

## 11. Safe-to-Cite Claims

- Implemented and evaluated a trustworthy enterprise document RAG-Agent with
  grounded scoring, ACL/state/conflict gates, citation binding, and real LLM
  evaluation.
- Real evaluation showed low false-answer tendency but substantial over-refusal
  and hard-negative retrieval failures.
- Agentic recovery was implemented and audited, but did not improve grounded
  correctness in the current full run.
- External retrieval ablation showed BM25/hybrid retrieval retrieved gold
  documents more reliably than vector-only on this split.

## 12. Unsafe-to-Cite Claims

- Agentic improves performance.
- The system is hard-negative robust.
- Citation accuracy is X% without manual audit.
- The reranker improves retrieval, because this ablation did not prove it.
- Grounded correctness is general QA accuracy without explaining the evaluation
  context and citation requirement.
- Raw correctness is system quality.

## 13. Remaining Q1 Blockers

- Manual citation support audit is still required.
- Hard-negative retrieval confusion needs mitigation or explicit disclosure.
- Gate calibration is needed to reduce false refusals while keeping the
  fail-closed safety posture.
- The agentic recovery claim must remain limited until a split shows measured
  improvement.

## 14. Whether Week 6 Can Be Committed

Week 6 can be committed as an honest evaluation milestone after this closeout
patch. It should be committed as evaluation/reporting completeness, not as a
performance optimization or final delivery package.

## 15. Recommended Next Step

Recommended next step: Week 7 engineering reproducibility after manual citation
audit planning. Do not begin deployment polish before citation-support audit
scope is accepted.
