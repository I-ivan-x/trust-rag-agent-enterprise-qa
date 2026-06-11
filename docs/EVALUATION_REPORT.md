# Evaluation Report

> Week 5B repair note: Previous obfuscated/agentic smoke results generated before the expected_rewrite isolation fix are invalidated and must not be cited.

Week 5B evaluation artifacts are present, but mock runs are smoke checks only.
Headline metrics require real embedding, real reranker, and real LLM providers.
expected_rewrite is informational only and is never used for retrieval or scoring.

## Latest Local Run

- run_id: `week5b-repair-fixture-real-retrieval`
- split: `fixture`
- systems: `vector_only, bm25_only, hybrid_rrf, hybrid_rrf_rerank`
- mode: `retrieval_only`
- headline_eligible: `False`
- toy_retrieval: `False`
- unavailable_systems: `{'hybrid_rrf_rerank': 'hybrid_rrf_rerank unavailable because BGE reranker could not be loaded; no mock fallback was used. original_error=BGE reranker loading is disabled for local eval by default to avoid implicit model downloads. Set EVAL_ENABLE_BGE_RERANK=1 after preparing the local BAAI/bge-reranker-base model cache.'}`

## Summary Metrics

```json
{
  "bm25_only": {
    "cases": 36,
    "deprecated_confusion": 0.3889,
    "doc_hit@5": 0.8611,
    "doc_recall": 0.8611,
    "hard_negative_error": 0.0,
    "hit@5": 0.8333,
    "mrr": 0.7593,
    "refusal_rate": 0.0
  },
  "hybrid_rrf": {
    "cases": 36,
    "deprecated_confusion": 0.7778,
    "doc_hit@5": 0.8611,
    "doc_recall": 0.8611,
    "hard_negative_error": 0.0,
    "hit@5": 0.8333,
    "mrr": 0.7778,
    "refusal_rate": 0.0
  },
  "vector_only": {
    "cases": 36,
    "deprecated_confusion": 0.8611,
    "doc_hit@5": 0.8611,
    "doc_recall": 0.8611,
    "hard_negative_error": 0.0,
    "hit@5": 0.8333,
    "mrr": 0.75,
    "refusal_rate": 0.0
  }
}
```

## Data Notes

- fixture split remains functional regression and is never headline.
- hard_negative split is a retrieval/citation robustness slice.
- obfuscated split compares final_gated and final_agentic behavior only.
- citation audit is rule-based v1 and requires human sampling before claims.
- external conflict cases use the existing active-active synthetic conflict group because the public FastAPI corpus has no native conflict_group_id overlay.

## External Coverage

```json
{
  "available": true,
  "case_count": 50,
  "expected_behavior_distribution": {
    "answer": 29,
    "refuse_no_evidence": 4,
    "refuse_permission": 10,
    "report_conflict": 2,
    "warn_deprecated": 5
  },
  "query_source_distribution": {
    "manifest_authored": 25,
    "real_user_question": 25
  },
  "query_type_distribution": {
    "citation_required": 4,
    "conflict_doc": 2,
    "deprecated_doc": 4,
    "fact_lookup": 21,
    "multi_doc_synthesis": 4,
    "no_evidence_or_out_of_scope": 4,
    "permission_denied": 4,
    "section_lookup": 7
  },
  "real_user_question_ratio": 0.5
}
```
