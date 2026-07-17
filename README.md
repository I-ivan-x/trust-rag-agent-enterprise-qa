# Agent Reliability Lab

**Governed Runtime, Evaluation Harness, and Decision Frontier for Tool-Using Agents**

Agent Reliability Lab is a reliability-first enterprise RAG and tool-using-agent laboratory. It combines fail-closed answer and action governance with a hash-bound evaluation system that reports positive results, negative results, and unmeasured questions at their actual evidence scope. **TrustRAG is the legacy codename** retained in internal identifiers, historical artifacts, run IDs, and release tags for reproducibility.

The current stable product release remains `v3.0-q4-reliability`. Q5 is a completed research track with overall status `scoped_negative_complete`; it does not create a new product release.

## What the repository demonstrates

- A RAG pipeline with deterministic ACL, state, evidence, citation, and refusal gates.
- A typed action runtime with capability checks, reauthorization, approval routing, and audited side effects.
- A reproducible evaluation harness with author isolation, leakage controls, pass^k, paired metrics, frozen protocol dispatch, and machine-enforced headline eligibility.
- A public truth layer: every current public claim is registered with scope, evidence mode, source SHA-256, run ID, evidence commit, limitations, and structured metrics.
- An honest Q5 conclusion: the selective runtime and efficiency were demonstrated within their frozen scopes, while preregistered LLM semantic uplift and controlled-prose LLM necessity were falsified in the current scope. Open-world LLM value was not evaluated.

## Current public results

`data/claims/claim_registry.json` is authoritative. The table below cites its claim IDs rather than maintaining a second fact table.

| Question | Current conclusion | Registry claim IDs |
| --- | --- | --- |
| Q1 | Fail-closed answer safety and hybrid retrieval uplift were demonstrated within the tracked real-run scope; conservative refusal remains a disclosed trade-off. | `q1.fail_closed_answers`, `q1.hybrid_retrieval` |
| Q2 | The measured agentic recovery gain was falsified in the evaluated real-run scope. | `q2.agentic_recovery` |
| Q3 | Action safety was demonstrated; the original selection-usefulness headline was falsified before Q4 calibration. | `q3.action_safety`, `q3.action_usefulness` |
| Q4 | Held-out calibrated selection and the governance safety floor were demonstrated within the frozen real-run scope. | `q4.calibrated_selection`, `q4.release_reliability` |
| Q5 | Selective runtime, observation adaptation, schema/transition safety, and real-dev hybrid efficiency were demonstrated within their named scopes. LLM semantic uplift and controlled-prose necessity were falsified in the current scope; open-world value was not evaluated. | `q5.selective_runtime_architecture`, `q5.observation_adaptation`, `q5.schema_transition_safety`, `q5.hybrid_efficiency`, `q5.llm_semantic_uplift`, `q5.controlled_prose_llm_necessity`, `q5.open_world_llm_value` |

See [Q5_FINAL_REPORT](docs/Q5_FINAL_REPORT.md) and the generated [Q5_CLAIM_MATRIX](docs/Q5_CLAIM_MATRIX.md) for the formal Q5 conclusion. Boundary F's original 30/32 result and the later addendum's frozen-scope 32/32 result remain separate, sequential evidence layers; the latter does not rewrite the former.

## Architecture

```text
ingest -> section-aware chunks
  -> dense retrieval || BM25 -> RRF -> rerank
  -> state gate -> ACL gate -> evidence gate
  -> bounded observation / typed proposal
  -> role + capability reauthorization
  -> validator -> approval or sink
  -> structured result + trace + manifest
```

The safety boundary is host-enforced: model output never bypasses the typed schema, action whitelist, authorization checks, Q4 validator, approval routing, or side-effect guard.

## Public claim workflow

Build and verify generated claims:

```powershell
py -m uv run --frozen python scripts/build_public_claims.py
py -m uv run --frozen python scripts/check_claim_drift.py
```

The generator owns:

- `docs/Q5_CLAIM_MATRIX.md`
- `docs/Q5_FINAL_REPORT.md`
- `docs/Q5_BOUNDARY_A_F_SUMMARY.md`
- `frontend/src/data/questions.json`
- `frontend/src/data/headline-results.json`
- `frontend/src/data/decision-frontier.json`
- `frontend/src/data/q5-evidence.json`
- `frontend/src/data/engineering-signals.json`

CI rejects schema violations, unknown statuses, duplicate claim IDs, missing ratio denominators, source/hash/run/commit spoofing, ignored-only evidence, and generated-file drift.

## Quick start

Docker smoke path:

```powershell
docker compose up -d --build
docker compose exec api python scripts/smoke_test.py --prepare --embedding-provider mock --require-vector --chat
```

Local uv path:

```powershell
py -m uv sync --locked --group dev
py -m uv run python scripts/ingest_corpus.py
py -m uv run python scripts/rebuild_indexes.py --embedding-provider mock
py -m uv run uvicorn app.main:app --reload
```

Open Swagger at <http://127.0.0.1:8000/docs> and the action-governance console at <http://127.0.0.1:8000/console/>. Mock output is for smoke and regression only; it is never headline evidence.

The recruiter-facing static showcase is in [`frontend/`](frontend/):

```powershell
cd frontend
npm ci
npm run build
```

## Verification status

Final Batch 5-Z verification: `908 passed, 1 skipped`. Ruff, claim drift, frontend build, and repository release gates are reported in the completion handoff.

## Documentation map

| Document | Purpose |
| --- | --- |
| [LATEST_RESULTS_AND_DEMO](docs/LATEST_RESULTS_AND_DEMO.md) | Current Q1–Q5 outcome and demo entry points |
| [PROJECT_OVERVIEW](docs/PROJECT_OVERVIEW.md) | Recruiter-facing engineering narrative |
| [Q5_FINAL_REPORT](docs/Q5_FINAL_REPORT.md) | Formal Q5 scoped conclusion |
| [Q5_CLAIM_MATRIX](docs/Q5_CLAIM_MATRIX.md) | Generated per-claim evidence map |
| [Q5_BOUNDARY_A_F_SUMMARY](docs/Q5_BOUNDARY_A_F_SUMMARY.md) | Current interpretation of the sequential diagnostic boundaries |
| [EVALUATION_REPORT](docs/EVALUATION_REPORT.md) | Evaluation history and current public-claim pointer |
| [FAILURE_ANALYSIS](docs/FAILURE_ANALYSIS.md) | Failure taxonomy and Q5 negative-result closure |
| [ENGINEERING_DISCIPLINE](docs/ENGINEERING_DISCIPLINE.md) | Evidence-driven delivery and anti-self-deception controls |
| [ROADMAP](docs/ROADMAP.md) | Historical evolution plus current closed Q5 state |
| [TECHNICAL_DESIGN](docs/TECHNICAL_DESIGN.md) | Architecture, threat model, and ADRs |

Historical Q5 plans and protocol reports remain available for audit, but any plan to create `q5_test`, enter K1, run a confirmatory provider, create Boundary G, or publish a Q5 tag is superseded. No such action is currently authorized.

## Evidence and release boundaries

- Current public claims must originate in the claim registry and tracked hash-bound artifacts.
- Evidence commits identify the implementation/run state that produced evidence; they are not self-referential “current documentation commits.”
- Historical run IDs, tags, artifact schemas, and internal TrustRAG identifiers are intentionally immutable.
- The latest stable tag is `v3.0-q4-reliability`; Q5 remains research evidence, not a tagged release.
- `q5_test` is absent and was not read or created during Q5 closure.
