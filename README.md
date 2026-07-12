# TrustRAG Enterprise QA

A trustworthy enterprise-document **RAG-Agent** with fail-closed trust gates,
plus an **anti-self-deception evaluation framework** -- which honestly measured
both the system's strengths (zero false answers, full auditability) and its
failures (over-refusal, a collapsed stress-test split, an agentic loop with no
measured gain), each with traced root causes.

**What this is**

- A QA pipeline whose trust properties are measured, not asserted: retrieval
  correctness, citation support, refusal behavior, state/ACL compliance, and
  auditability.
- An evaluation governance system: corpus/eval author isolation, leakage
  checks, contamination-isolating grounded scoring, and machine-enforced rules
  about which numbers may be reported.
- An honest results report. The negative findings below are not hidden; they
  are the project's strongest evidence of being real.

**What this is not**

- Not a chatbot wrapper or a LangChain tutorial walkthrough.
- Not a leaderboard project: the headline metric is deliberately the hardest
  one we could define (`grounded_correctness`), not the prettiest.
- Not an autonomous agent: the "Agent" is a bounded, policy-constrained, fully
  traced evidence-recovery loop. The current report says plainly that this loop
  has not yet earned its keep.

------

## Honest Results at a Glance

All numbers from Week 6 **real runs**: real embedding (`bge-small-en-v1.5`),
real reranker (`bge-reranker-base`), real LLM (DeepSeek), public external
corpus (FastAPI docs subset, 50 evaluation cases). Full run inventory:
[EVALUATION_REPORT](docs/EVALUATION_REPORT.md).

### What works (measured)

| Result | Number | Scope |
| --- | --- | --- |
| False answers on external real run | **0.00** | Fail-closed gates: the system answered nothing it could not cite |
| Citation structural validity | **1.00** | Every citation id verifiably from retrieved context; fabricated ids are blocked. This is structural validity, not human-audited support. |
| Hybrid retrieval vs vector-only | doc_hit@5 **0.60 -> 0.80** | The one retrieval improvement the ablation actually supports |
| Contamination control | direct LLM raw **0.20** -> grounded **0.00** | The model knows some public-corpus content from training, but cannot convert that into cited evidence |
| Final system retrieval | doc_hit@5 0.76, MRR 0.61 | External split, end-to-end |
| Action governance (Q3) | unauthorized-action blocked **1.00**, F11/F13 **0** | Real ops run: zero unauthorized and zero no-evidence side effects; fail-closed promoted from answers to actions |
| Action selection, calibrated (Q4) | precision@authorized 0.4545 → **0.6471** (held-out); anti-gaming triad **False → True** | The Q3 negative turned positive by fixing real defects (dead `flag_stale` path, over-escalation), thresholds frozen, F11/F13 still 0. Real but thin: clears by ~1 case (11/17); 6/17 residual is small-corpus retrieval, disclosed. Proven on a held-out set the calibration never tuned on. |

### What fails (measured, with root cause)

| Result | Number | Root cause and status |
| --- | --- | --- |
| Grounded correctness | **0.24**, with false-refusal **0.46** | The price of fail-closed gating: the bottleneck is not answering, not answering wrong. Gate calibration is the next planned phase. |
| Agentic recovery gain | **none proven** | Q2 built the typed action space (rewrite / filter / conflict / refuse) and ran a rule-vs-LLM controller ablation (n=22): gated 0.2273 vs agentic 0.2727 — a one-case delta, rule==LLM, diagnostic-only. The calibrated system's residual failures are policy-adjudication, not retrieval-recoverable. |
| Reranker contribution | doc_hit@5 0.80 -> **0.78** | Not proven; no rerank improvement is claimed anywhere in this project. |
| Hard-negative stress test | error rate **1.0** | Pre-digested adjudication attributes this to an eval design flaw: all 20 queries were metadata-only templates with zero content words. Retrieval robustness is currently unknown, not bad; owner sign-off and re-validation with rewritten queries are pending. |
| Action selection usefulness (Q3) | precision **~0.55**, anti-gaming triad **False** | The safety layer is airtight, but the controller over-escalates (F12=25) and the `flag_stale` path is dead; the triad gate correctly refused the usefulness headline. **Resolved in Q4** (triad flipped True on a held-out set — see "What works"). rule≈llm — same boundary as Q2. |

Every failure row links to a root-cause analysis in
[FAILURE_ANALYSIS](docs/FAILURE_ANALYSIS.md) (taxonomy F1-F13) and a planned fix
in [ROADMAP](docs/ROADMAP.md).

------

## Architecture

```text
ingest (markdown/txt + front matter + metadata overlay)
  -> section-aware chunking
  -> dense retrieval (Qdrant) || BM25 (Whoosh) -> RRF fusion -> BGE rerank
  -> state gate -> ACL gate -> evidence gate
       -> if evidence insufficient and not policy-blocked:
            one query rewrite -> second-pass retrieval -> all gates again
  -> conflict detection -> context assembly
  -> grounded generation (claims + supporting_chunk_ids)
  -> citation binding (context-only ids) -> structural verification
  -> refusal controller (permission > conflict > deprecated > answer/no-evidence)
  -> JSONL trace
```

Design rationale and the measured consequence of every major decision:
[TECHNICAL_DESIGN](docs/TECHNICAL_DESIGN.md).

## Why You Can Trust These Numbers

1. **Grounded-only headline.** An answer scores only if it is correct, every
   citation comes from retrieved context, and a citation supports the core
   claim. Parametric memory cannot cheat this metric.
2. **No circular validation.** Corpus authors and eval authors are
   process-isolated; queries pass automated leakage checks; half the external
   queries come from real user questions.
3. **Reporting eligibility is code, not discipline.** Run summaries carry
   `headline_eligible` and `mock_used` flags guarded by unit tests; mock or
   partial runs are mechanically excluded from headline reporting.
4. **The governance system audits itself.** The hard-negative split failure was
   traced to the eval's own query design and reported as such, with the protocol
   fix documented.
5. **Standardized, gated reliability.** Pipeline traces export to OpenInference span
   kinds over OTLP with OpenTelemetry GenAI attributes (opt-in `--otel`); each run emits
   a reproducibility manifest (model, index fingerprint, corpus namespace, seed, k,
   commit SHA); and the reliability contracts (F11=0, F13=0, leakage=0, mock≠headline,
   triad-gates-usefulness) are enforced as CI hard gates.

## Quick Start

Docker smoke path:

```powershell
docker compose up -d --build
docker compose exec api python scripts/smoke_test.py --prepare --embedding-provider mock --require-vector --chat
```

The compose stack starts the FastAPI API and an internal Qdrant service. It
defaults to mock embedding/reranker/LLM providers so the demo starts without
model downloads or API keys. Mock output is for local smoke only and must not
be reported as formal evaluation.

Local uv path:

```powershell
python -m uv sync
python -m uv run python scripts/ingest_corpus.py
python -m uv run python scripts/rebuild_indexes.py --embedding-provider mock
python -m uv run uvicorn app.main:app --reload
```

Open Swagger UI at <http://127.0.0.1:8000/docs>, and the Q3 action-governance
console (读 → 判 → 动 → 治 timeline, approval queue, audit trail, blocked log) at
<http://127.0.0.1:8000/console/>.

A recruiter-facing **showcase** of the full Q1–Q4 narrative (premium dark,
snapshot-first, interactive trajectory player) lives in [`frontend/`](frontend/):
`cd frontend && npm install && npm run dev`.

Useful Make targets:

```powershell
make sync
make lint
make test
make docker-smoke
```

For real embedding/reranker experiments, build the optional model runtime and
mount the Hugging Face cache through the compose volume. Compose intentionally
uses `DOCKER_*` override variables so local `.env` evaluation keys do not leak
into smoke containers by accident:

```powershell
$env:INSTALL_SENTENCE_TRANSFORMER="true"
$env:DOCKER_EMBEDDING_PROVIDER="sentence_transformer"
$env:DOCKER_RERANKER_PROVIDER="bge"
docker compose build
```

## Reproducing the Evaluation

```powershell
python -m uv run python scripts/check_eval_leakage.py --all
python -m uv run python scripts/run_eval.py --split external --systems vector_only,bm25_only,hybrid_rrf,hybrid_rrf_rerank --retrieval-only
python -m uv run python scripts/run_eval.py --split external --systems direct_llm,final_gated,final_agentic --real-run
python -m uv run python scripts/run_eval.py --split obfuscated --systems final_gated,final_agentic --real-run
```

Real runs require a DeepSeek-compatible API key in `.env` (see
`.env.example`). Retrieval-tier runs make zero LLM calls. Each run writes
`results.jsonl`, `traces.jsonl`, `failures.jsonl`, and a `summary.json` whose
`headline_eligible` field states whether it may be cited.

## Documentation

| Document | Content |
| --- | --- |
| [TECHNICAL_DESIGN](docs/TECHNICAL_DESIGN.md) | Threat model and ADRs with measured consequences |
| [LATEST_RESULTS_AND_DEMO](docs/LATEST_RESULTS_AND_DEMO.md) | Latest Q1-Q4 outcome summary plus the two web demo entry points (`/console/` and `frontend/`) |
| [ENGINEERING_DISCIPLINE](docs/ENGINEERING_DISCIPLINE.md) | Evidence-backed record of planning, scope control, evaluation discipline, AI collaboration, and delivery efficiency |
| [Q5_ADAPTIVE_AGENT_DESIGN](docs/Q5_ADAPTIVE_AGENT_DESIGN.md) | Active Q5 plan: selective hybrid Agent, semantic decision frontier, bounded observation loop, and outcome-based eval |
| [Q5_P5_PREREG_AMENDMENT_V2](docs/Q5_P5_PREREG_AMENDMENT_V2.md) | Test-before-seeing amendment for protocol-v2, trajectory-qualified gates, counterfactual q5_dev, and v1 artifact preservation |
| [Q5_P5_DEV_V2_READINESS](docs/Q5_P5_DEV_V2_READINESS.md) | C1R/C3 audits, v2 authoring receipt, and the failed primary real-dev freeze decision |
| [Q5_P5_REAL_DEV_V2_NEGATIVE_DIAGNOSTIC](docs/Q5_P5_REAL_DEV_V2_NEGATIVE_DIAGNOSTIC.md) | Real trajectory diagnosis: repeated observations, fixed-table semantics, G1/G3 failure, and v3 direction |
| [SPEC_Q5_P5_E_AGENT_VALIDITY](docs/SPEC_Q5_P5_E_AGENT_VALIDITY.md) | Large implementation batch for observation idempotency, strong-rule audit, replay diagnostics, and protocol-v3 groundwork |
| [EVALUATION_REPORT](docs/EVALUATION_REPORT.md) | Week 6 results, contamination analysis, trade-off discussion, Q2 Phase 1 calibration, and the Q3 action-governance ablation |
| [FAILURE_ANALYSIS](docs/FAILURE_ANALYSIS.md) | Failure taxonomy F1-F13 with trace evidence |
| [Q3_ACTION_GOVERNANCE_DESIGN](docs/Q3_ACTION_GOVERNANCE_DESIGN.md) | Q3 action-governance design freeze (evidence-aware ops copilot, risk-tiered autonomy) |
| [Q4_RELIABILITY_DESIGN](docs/Q4_RELIABILITY_DESIGN.md) / [Q4_P2_PREREGISTER](docs/Q4_P2_PREREGISTER.md) | Q4 selection-calibration (negative→positive) design, pre-registered gate, and held-out discipline |
| [SPEC_Q4_P6_P7](docs/SPEC_Q4_P6_P7.md) | OpenInference/OTel trace exporter, run manifest, and CI hard-gate spec |
| [HARD_NEGATIVE_ADJUDICATION](docs/HARD_NEGATIVE_ADJUDICATION.md) | Why the stress-test split collapsed, and the re-validation plan |
| [CITATION_AUDIT](docs/CITATION_AUDIT.md) / [GUIDE](docs/CITATION_AUDIT_GUIDE.md) | Rule-based audit status, manual census, and audit protocol |
| [EVAL_PROTOCOL](docs/EVAL_PROTOCOL.md) / [CORPUS_PROTOCOL](docs/CORPUS_PROTOCOL.md) | Author isolation and corpus governance |
| [ROADMAP](docs/ROADMAP.md) | Q1-Q5 evolution: trustworthy RAG, typed actions, action governance, reliability calibration, and adaptive hybrid Agent |

## Data Sources and Boundaries

- **Public external corpus**: a subset of public FastAPI documentation. Document
  text is unmodified; ACL/state/conflict metadata is a controlled, seeded
  overlay declared in every report that uses it.
- **Synthetic fixture corpus**: authored for functional regression only; never
  reported as headline metrics.
- **Hard negatives**: adjacent/similar pages from the public corpus.
- Evaluation artifacts referenced by reports are archived per run id.
