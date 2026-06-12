# Technical Design — TrustRAG Enterprise QA

Status: Q1 closeout version. Decision records are append-only: Q2 work adds new
ADRs and never rewrites Q1 ADRs.

All numbers cited here come from Week 6 real runs (DeepSeek `deepseek-v4-flash`,
`bge-small-en-v1.5` embedding, `bge-reranker-base`). Run inventory:
[EVALUATION_REPORT.md](EVALUATION_REPORT.md).

------

## 1. Problem & Goals

Enterprise document QA fails differently from open-domain QA: the corpus
contains stale versions, access-restricted content, and conflicting documents,
and a wrong-but-confident answer is more expensive than no answer. The goal of
Q1 was **not** to maximize answer coverage, but to build a pipeline whose
trust properties — retrieval correctness, citation support, refusal behavior,
state/ACL compliance, auditability — are *measured* rather than asserted.

Non-goals for Q1 (frozen in the task plan): PDF parsing, real SSO/ACL,
multi-tenant, free-planning multi-agent, fine-tuning, cloud deployment,
frontend. None of these prove the core trust-engineering claim.

## 2. Threat Model

The design is a point-by-point response to six failure threats:

| # | Threat | Control |
| --- | --- | --- |
| T1 | Hallucinated / unsupported answers | Evidence gate + citation binding + grounded-only scoring (ADR-002, ADR-003) |
| T2 | Stale or deprecated content answered as current | Document state gate, `warn_deprecated` mode (ADR-001) |
| T3 | Access-restricted content leaking to unauthorized roles | ACL gate, applied after retrieval and re-applied after any second pass (ADR-001, ADR-004) |
| T4 | Fabricated citations (LLM invents chunk ids) | Citation binder restricted to ContextPack ids (ADR-003) |
| T5 | Conflicting active documents merged into one confident answer | Minimal active-active conflict detection, `report_conflict` mode (ADR-001) |
| T6 | Evaluation self-deception (circular validation, contamination, mock numbers) | Corpus/eval author isolation, leakage checks, grounded headline, headline-eligibility code contract (ADR-002, ADR-005, ADR-007) |
| T7 | Corpus poisoning / indirect prompt injection | **Acknowledged, untested in Q1.** Planned as a measured red-team split in Q2 ([ROADMAP.md](ROADMAP.md) P2-07). |

T6 is unusual in this list: it treats the project's own evaluation as a system
that can fail, and it did fail once in a measurable way (see ADR-005).

## 3. Architecture Overview

```text
ingest (markdown/txt + front matter + metadata overlay)
  → section-aware chunking
  → dense retrieval (bge-small-en-v1.5 / Qdrant) ∥ BM25 (Whoosh)
  → RRF fusion → cross-encoder rerank (bge-reranker-base)
  → document state gate → ACL gate → evidence gate
       └─ if evidence insufficient (and not policy-blocked):
            single query rewrite → second-pass retrieval → all gates again
  → minimal conflict detection
  → context assembly → grounded answer generation (claims + supporting_chunk_ids)
  → citation binding (ContextPack-only ids) → structural citation verification
  → refusal controller (priority: permission > conflict > deprecated > answer/no-evidence)
  → JSONL trace (per-pass retrieval, gate decisions, rewrite events, final decision)
```

Evaluation sits beside the pipeline as a first-class subsystem: four splits,
two baseline tiers, grounded scoring, and machine-checked reporting eligibility.

------

## 4. Architecture Decision Records

Each ADR carries the same four sections. "Measured consequence" is the part
most design docs omit: what the decision actually cost or bought in the Week 6
full real runs.

### ADR-001 — Fail closed, with a fixed refusal priority

**Decision.** All gates fail closed. The refusal controller resolves competing
signals with a fixed priority: `refuse_permission > report_conflict >
warn_deprecated > answer / refuse_no_evidence`.

**Rationale.** In enterprise QA the cost asymmetry is structural: a false
answer about permissions, compliance, or versions is an incident; a false
refusal is an inconvenience. Before any calibration data existed, the only
defensible default was maximum safety. Phase 1 ships fail-closed and measures
the cost; phase 2 calibrates from that data. The sequencing is deliberate.

**Measured consequence.** External full run (50 cases):
`false_answer_rate = 0.00` and `citation_valid = 1.00` — the safety goal was
met. The measured price: `refusal_rate = 0.74`, `false_refusal_rate = 0.46`,
capping `grounded_correctness` at 0.24. Failure analysis attributes most of it
to F1/F2: restricted or deprecated *neighbors* in the retrieved set trigger
gates even when clean evidence exists.

**Calibration path.** Q2 Phase 1: evidence-gate threshold sweep plus a policy
variant distinguishing "a deprecated neighbor is present" from "only deprecated
evidence is available", reported as a false-refusal vs false-answer trade-off
curve. Citation and grounding requirements are not relaxed.

### ADR-002 — Headline metric is grounded correctness only

**Decision.** The only headline answer metric is `grounded_correctness`:
the answer must be correct **and** every citation must come from the
ContextPack **and** at least one citation must support the core claim. Raw
correctness is reported only as a contamination signal
(`parametric_leakage_gap = raw − grounded`).

**Rationale.** The external corpus is public FastAPI documentation, plausibly
inside the LLM's training distribution. An answer-only metric would let
parametric memory masquerade as retrieval quality. Grounded scoring closes
that route: memorized knowledge cannot produce valid citations.

**Measured consequence.** The control worked exactly as designed:
`direct_llm` scored `raw = 0.20` but `grounded = 0.00` on the external split —
the model demonstrably knows some of the corpus and demonstrably cannot turn
that into cited evidence. Raw numbers are never quoted as system quality.

**Calibration path.** Held-out / private corpora for contamination-resistant
evaluation in a later quarter.

### ADR-003 — Citations are bound, verified structurally, and audited manually

**Decision.** The generator must emit claims with `supporting_chunk_ids`; the
citation binder rejects any id not present in the ContextPack. Verification v1
is rule-based (structural validity). Human claim-level support is established
only by a manual audit protocol
([CITATION_AUDIT_GUIDE.md](CITATION_AUDIT_GUIDE.md)), never by the rule-based
check.

**Rationale.** "Sources at the end of the answer" is decoration, not
citation. Binding at claim granularity makes fabricated evidence mechanically
impossible (T4) and makes claim-level auditing possible at all.

**Measured consequence.** `citation_valid = 1.00` on the external real run —
and the hard-negative run shows precisely why this number must not be oversold:
there, `citation_valid = 1.00` coexists with `grounded_correctness = 0.00`,
because a citation can be structurally valid while pointing at the wrong
document of a confusable pair (failure class F4). A second consequence was
discovered during audit preparation: Week 6 run artifacts did not persist
answer text or claim→citation bindings, blocking the manual audit until a
persistence patch and re-run land (ROADMAP C1-00). Lesson recorded in ADR-008.

**Calibration path.** Manual audit (25–40 claims, blind one-week re-label),
then a human-anchored LLM judge compared against RAGAS/DeepEval on the same
anchors (Q2 Phase 2).

### ADR-004 — Agentic recovery is bounded and cannot bypass policy

**Decision.** The "Agent" in the system name is a workflow-bounded recovery
loop: triggered only by the evidence gate, at most one rewrite and one
second-pass retrieval, mandatory stop conditions, full trace, and a hard rule
that rewriting can never bypass ACL or state gates — permission-blocked
queries are refused without recovery.

**Rationale.** Unbounded self-reflection loops are unauditable and can launder
policy violations through reformulation. Constrained autonomy is the only kind
an enterprise can deploy; it is also falsifiable, which free-form agency is
not.

**Measured consequence.** The constraint system worked (zero gate bypasses,
zero runaway loops). The benefit did not materialize: on the obfuscated split
`final_gated` and `final_agentic` tied at `grounded_correctness = 0.3333`,
with one rewrite LLM call and no accepted rewrite. Root cause (F5): most
refusals travel permission/deprecated/conflict paths where rewriting is
forbidden by design, so the single available action had almost no trigger
surface. The negative result identified the real bottleneck ordering:
calibrate gates first, then expand the action space.

**Calibration path.** Q2 Phase 3: typed action space (rewrite,
metadata-filtered re-retrieval, version-scoped retrieval — conditional on
hard-negative re-validation confirming F3 — conflict-set presentation,
explained refusal), diagnosis-driven selection, rule-vs-LLM controller
ablation under identical constraints, per-action (trajectory-level)
attribution, and pass^k reliability reporting.

### ADR-005 — Three corpora, four splits, author isolation, leakage checks

**Decision.** Synthetic fixtures (functional regression only), public external
corpus (headline), hard negatives (stress), obfuscated variants (agentic
ablation). Corpus authors and eval authors are process-isolated; queries pass
an automated leakage check (title overlap, answer-sentence copying); ≥50% of
external queries come from real user questions.

**Rationale.** Self-authored corpora evaluated by self-authored queries is
circular validation — the default failure mode of student RAG projects. The
split system assigns each kind of evidence a scope it cannot exceed.

**Measured consequence.** The isolation protocol held for the external split.
The governance system then **caught its own blind spot**: all 20 hard-negative
queries followed a metadata-only template ("answer from side A of group X")
containing zero content words. The leakage check guards against queries
carrying *too much* information and was silent about queries carrying *none*;
retrieval collapsed identically across all 20 cases
(`hard_negative_error_rate = 1.0`, `doc_hit@5 = 0.05`), and adjudication
attributes the failure to eval design (F8), with genuine retrieval weakness
(F3) untested pending rewritten queries
([HARD_NEGATIVE_ADJUDICATION.md](HARD_NEGATIVE_ADJUDICATION.md)).

**Calibration path.** Two-sided query bounds in the protocol (too much
information = leakage; zero information = unretrievable), mandatory human read
of sampled queries before any split freezes, rewritten hard-negative queries
re-validated at zero LLM cost.

### ADR-006 — Layered baselines; claim only what the ablation shows

**Decision.** Baselines are split into a retrieval tier (zero LLM calls:
vector / BM25 / hybrid RRF / hybrid+rerank) and an end-to-end tier (real LLM:
direct LLM / final gated / final agentic). Any capability not demonstrated by
its ablation is not claimed anywhere — README, report, or resume.

**Rationale.** Seven systems × full real LLM evaluation would have exploded
cost and review time; retrieval questions don't need an LLM to answer.
The claim discipline exists because ablations sometimes return unwelcome
answers, and the project's credibility rests on reporting those.

**Measured consequence.** One clean positive: hybrid retrieval lifted
`doc_hit@5` from 0.60 (vector-only) to 0.80. One unwelcome answer, reported as
such: adding the reranker *lowered* `doc_hit@5` to 0.78 and MRR from 0.640 to
0.611 — so no rerank improvement is claimed in any project material.
Plausible causes (generic-domain cross-encoder, 442-chunk corpus,
keyword-friendly real-user queries) are recorded as hypotheses, not findings.

**Calibration path.** Domain validation of rerankers; metadata-aware and
version-aware reranking experiments in Q2.

### ADR-007 — Reporting eligibility is a code contract, not a convention

**Decision.** Every run summary carries machine-readable provenance:
`headline_eligible`, `headline_scope`, `mock_used`, `toy_retrieval`,
`expected_rewrite_used`, `llm_call_count`. Unit tests enforce that mock or
partial runs can never be marked headline-eligible. Mocks exist for CI and
smoke tests only; reported metrics require real embedding, reranker, and LLM.

**Rationale.** "We promise not to quote mock numbers" does not survive contact
with deadline pressure. A schema field guarded by tests does.

**Measured consequence.** The Week 6 fixture regression (36/36 cases, mock,
zero LLM calls) is automatically excluded from headline reporting; its
`grounded = 0.3889` exists in artifacts but cannot be cited. The contract has
already prevented one class of accidental dishonesty at zero marginal cost.

**Calibration path.** Q2 extends the contract with a `judge_based` label so
LLM-judge metrics can never be conflated with human-audited ones.

### ADR-008 — Tracing is full-chain, and must persist what governance consumes

**Decision.** Every query writes a JSONL trace: per-pass retrieval ids, gate
decisions, rewrite events, model/provider, final decision. Q1 scoped trace
content to *decisions*; answer content was not persisted.

**Rationale.** Auditability (T6) requires replaying why the system answered or
refused. Decision-level tracing seemed sufficient for that.

**Measured consequence.** The scoping was proven too narrow: the manual
citation audit needs (claim, cited-chunk) pairs, which were generated at run
time and discarded — none of the Week 6 artifacts contain them, blocking the
audit until a persistence patch and a ~85-call re-run land (ROADMAP C1-00).
General lesson: **trace schema must be derived from what downstream
governance consumes, not from what the pipeline finds convenient to log.**

**Calibration path.** Persist `answer_text`, `claims[].text`,
`claims[].supporting_chunk_ids` in run artifacts; Q2 aligns trace fields with
agent actions (trajectory-level attribution) and, when budget allows, the
OpenTelemetry GenAI semantic conventions.

------

## 5. Measured Trade-offs — Summary

| Trade-off | Chosen side | Measured cost | Measured benefit |
| --- | --- | --- | --- |
| False answer vs false refusal | Fail closed | false_refusal 0.46, grounded capped at 0.24 | false_answer 0.00, citation_valid 1.00 |
| Coverage vs contamination resistance | Grounded-only headline | Headline looks worse than answer-only metrics would | Parametric memory provably excluded (0.20 raw → 0.00 grounded) |
| Agent autonomy vs auditability | Bounded single-action loop | No measured recovery gain (tie at 0.3333) | Zero gate bypasses; falsifiable agent claims |
| Pipeline richness vs ablation honesty | Claim-only-what's-shown | Rerank cannot be claimed | One clean, defensible retrieval claim (0.60 → 0.80) |

The calibration roadmap for every row lives in [ROADMAP.md](ROADMAP.md).

## 6. Limitations

- Single LLM family (DeepSeek) for all end-to-end runs; judge work in Q2 will
  introduce a second family by methodological necessity.
- Manual citation-support audit pending (blocked on ADR-008 persistence gap);
  until it lands, only structural citation validity may be cited.
- Hard-negative retrieval robustness is currently **unknown**, not bad: the
  Q1 split design flaw (ADR-005) means the stress test must be re-run with
  rewritten queries before any F3 conclusion.
- External split is 50 cases; per-type percentages below n=5 are reported as
  case studies only.
- ACL/state metadata on the public corpus is a controlled overlay (declared in
  the report), not native enterprise metadata.
- Indirect prompt injection (T7) is acknowledged and untested until the Q2
  red-team split.
