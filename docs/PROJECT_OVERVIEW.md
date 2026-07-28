# Agent Reliability Lab — Project Overview

> **Governed Runtime, Evaluation Harness, and Decision Frontier for Tool-Using Agents**

Agent Reliability Lab is an owner-led, AI-assisted reliability and evaluation project for enterprise RAG and tool-using agents. The Owner retained scope, labeling, protocol-freeze, trade-off, and acceptance authority; Codex and Claude accelerated implementation, analysis, and documentation under machine-enforced review gates. **TrustRAG is the legacy codename** preserved in internal identifiers, historical artifacts, run IDs, and tags. The public identity changed; the evidence chain did not.

The differentiator is not a larger agent loop. It is an engineering system that makes answers, actions, experiments, and public claims measurable, auditable, regression-gated, and explicit about scope.

## Five-question arc

All current result statements below point to `data/claims/claim_registry.json`. The registry, not this narrative, is the numeric source of truth.

| Question | Engineering question | Current answer | Claim IDs |
| --- | --- | --- | --- |
| Q1 | Can an enterprise RAG system fail closed without hiding the refusal cost? | Answer safety and hybrid retrieval were demonstrated within the tracked real-run scope; conservative refusal remains disclosed. | `q1.fail_closed_answers`, `q1.hybrid_retrieval` |
| Q2 | Does a typed recovery agent materially improve the measured task? | No in the evaluated scope; the proposed agentic recovery gain was falsified rather than promoted. | `q2.agentic_recovery` |
| Q3 | Can the trust boundary govern side effects as well as text? | Action safety was demonstrated, while the first usefulness gate correctly failed. | `q3.action_safety`, `q3.action_usefulness` |
| Q4 | Can a diagnosed selection defect be fixed without relaxing safety or the gate? | Calibrated selection and the safety floor were demonstrated in the disclosed second run over frozen `ops_test`; this is not a pristine one-shot holdout. | `q4.calibrated_selection`, `q4.release_reliability` |
| Q5 | Where does a selective tool-using LLM add value over strong deterministic controls? | Runtime/safety/efficiency mechanisms worked, but semantic uplift and controlled-prose necessity were falsified in the current scope. Open-world value was not evaluated. | `q5.selective_runtime_architecture`, `q5.observation_adaptation`, `q5.schema_transition_safety`, `q5.hybrid_efficiency`, `q5.llm_semantic_uplift`, `q5.controlled_prose_llm_necessity`, `q5.open_world_llm_value` |

Q5's overall status is `scoped_negative_complete`. Boundary F's original 30/32 result remains frozen, and the versioned addendum separately reaches 32/32 in the frozen K0U parser-uncovered scope. This closes the controlled-prose track; it does not generalize to open-world language.

## Engineering system

1. **Grounded answer contract.** Retrieval, ACL/state filtering, evidence sufficiency, citation binding, and refusal are host-enforced.
2. **Governed action contract.** Typed proposals pass role/capability reauthorization, the existing Q4 validator, risk-tiered approval, and a side-effect guard.
3. **Bounded observation loop.** Tools are read-only, arguments are provenance-checked, observations are typed, and untrusted text cannot become a trusted policy fact.
4. **Evaluation governance.** Dataset/runtime/gold boundaries, frozen protocol dispatch, paired metrics, bootstrap, analytic controls, and mutation tests make result tampering fail closed.
5. **Public truth layer.** Current claims carry source path, SHA-256, run ID, evidence commit, evidence mode, scope, limitations, and headline eligibility. Generated docs/frontend data cannot drift silently.

## Recruiter-ready bullets

- Built a fail-closed enterprise RAG and action-governance runtime with separately measured answer and side-effect safety (`q1.fail_closed_answers`, `q3.action_safety`).
- Designed an evaluation harness that separates execution from sealed-gold grading, verifies complete trial matrices, preserves frozen protocol generations, and rejects mutated artifacts.
- Converted a weak action-selection result into a scoped frozen-`ops_test`
  second-run improvement without changing the safety floor or frozen gate,
  while preserving the first failure and mechanism correction
  (`q4.calibrated_selection`, `q4.release_reliability`).
- Implemented a selective LLM/rule/hybrid runtime with typed tools, bounded trajectories, provenance-aware context, OTel-compatible events, and real-dev efficiency evidence (`q5.hybrid_efficiency`).
- Attacked the project's own Q5 value claim through fixed-table, symbolic, parser, shortcut, and post-hoc deterministic challengers; closed the controlled-prose track when those controls eliminated the apparent headroom (`q5.controlled_prose_llm_necessity`).
- Added a machine-readable public claim registry and CI drift gate so recruiting copy cannot outrun tracked evidence.

## How to discuss the negative Q5 result

The correct claim is narrow and useful:

> The two scoped negatives are separate. In the current real-dev semantic
> stratum, preregistered LLM uplift reached only 1/12 and failed its gate.
> Separately, in the frozen controlled-prose K0U scope, a runtime-only parser
> resolved 32/32 cases, falsifying LLM necessity there. Neither result evaluates
> open-world LLM value.

The engineering value is the ability to discover that a benchmark is too easy, preserve each negative boundary without rewriting history, and stop before spending more provider calls or creating a test split that cannot answer the intended question.

## Verification and release boundary

- Final local-archive regression: `975 passed, 3 skipped`.
- The detached clean clone passed three consecutive Lighthouse performance
  runs at or above `90`, accessibility `100/100/100`, Playwright
  `55 passed / 14 conditionally skipped`, and release gates `6/6`; exact
  per-run performance scores remain in the receipt.
- `data/releases/release_manifest_v2.json` binds the tested commit/tree, locks,
  claims, reports, Boundary F evidence, public audit, frontend receipt, and
  clean-clone receipt; CI rejects drift.
- The current npm production and development audit is clean after the
  non-breaking Lighthouse 13.4.1 patch.
- Latest stable product release: `v3.0-q4-reliability`.
- Q5 creates no product release: K1, Boundary G, new K1 data, `q5_test`, and
  confirmatory runs are not authorized. The exact annotated tag
  `agent-reliability-lab-q5-closed-20260717` is a non-product research marker;
  it does not create `v4.0`.
- Evidence commits in the registry identify evidence-producing states; they are not claims about the commit containing this document.

## Pointers

- Current truth layer: [Claim registry](../data/claims/claim_registry.json), [Q5 Claim Matrix](Q5_CLAIM_MATRIX.md)
- Formal Q5 conclusion: [Q5 Final Report](Q5_FINAL_REPORT.md)
- Boundary interpretation: [Boundary A–F Summary](Q5_BOUNDARY_A_F_SUMMARY.md)
- Latest results and demos: [Latest Results and Demo](LATEST_RESULTS_AND_DEMO.md)
- Full evaluation history: [Evaluation Report](EVALUATION_REPORT.md)
- Failure taxonomy: [Failure Analysis](FAILURE_ANALYSIS.md)
- Engineering process: [Engineering Discipline](ENGINEERING_DISCIPLINE.md)
- Exact 180-second demo: [Three-Minute Demo Script](THREE_MINUTE_DEMO_SCRIPT.md)
- Role-specific resume wording: [Resume Bullets](RESUME_BULLETS.md)
- Archive/maintenance contract: [Project Archive and Maintenance](PROJECT_ARCHIVE_AND_MAINTENANCE.md)
- Runtime demo: `uvicorn app.main:app` then `/console/`
- Static showcase: `cd frontend && npm ci && npm run build`
