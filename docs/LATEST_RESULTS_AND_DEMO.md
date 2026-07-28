# Agent Reliability Lab — Latest Results and Demo

**Governed Runtime, Evaluation Harness, and Decision Frontier for Tool-Using Agents**

Current as of 2026-07-28. TrustRAG is the legacy codename retained in historical artifacts and internal identifiers. The latest stable product release remains `v3.0-q4-reliability`; Q5 is closed as research evidence with overall status `scoped_negative_complete`.

## Current result map

All result rows explicitly reference canonical claim IDs in `data/claims/claim_registry.json`. Evidence commits name the code/run state that produced each receipt; they are not the commit of this document.

| Stage | Current conclusion | Claim IDs |
| --- | --- | --- |
| Q1 | Fail-closed answer safety and hybrid retrieval uplift were demonstrated within the tracked real-run scope, with refusal cost disclosed. | `q1.fail_closed_answers`, `q1.hybrid_retrieval` |
| Q2 | Agentic retrieval recovery did not establish a meaningful gain in the evaluated real-run scope. | `q2.agentic_recovery` |
| Q3 | Governed-action safety was demonstrated; the first selection-usefulness gate failed as intended. | `q3.action_safety`, `q3.action_usefulness` |
| Q4 | Calibrated action selection and the safety floor were demonstrated in the disclosed second run over frozen `ops_test`; the first failure and correction remain archived. | `q4.calibrated_selection`, `q4.release_reliability` |
| Q5 | Selective runtime, observation adaptation, schema/transition safety, and real-dev hybrid efficiency were demonstrated within their named scopes. Semantic uplift and controlled-prose LLM necessity were falsified in the current scope; open-world value was not evaluated. | all seven `q5.*` claims in `docs/Q5_CLAIM_MATRIX.md` |

## Q5 formal closure

The original Boundary F and its addendum are sequential evidence, not competing rewrites:

- Original frozen Boundary F: 30/32 parser-uncovered cases recovered.
- Versioned addendum: 32/32 recovered in the frozen K0U parser-uncovered scope, with coverage 1.0, conditional risk 0.0, and zero abstentions.
- The addendum made zero model requests and zero external requests.
- `controlled_prose_track=closed`; `K1=false`; Boundary G and new K1 data are prohibited.
- The real-dev Hybrid/LLM-only efficiency result remains evidence, while the preregistered semantic uplift was below threshold.
- `q5_test` is absent and was not read or created during closure.
- Open-world LLM value remains `not_evaluated`; the controlled-prose result must not be generalized.

These values are generated from `q5.controlled_prose_llm_necessity`, `q5.hybrid_efficiency`, and `q5.llm_semantic_uplift`. See `docs/Q5_FINAL_REPORT.md` for the generated formal wording.

## Demo entry points

### Runtime governance console

The FastAPI console shows the live read → detect → propose → validate → approve/commit path, including pending approval, audit trail, and blocked actions.

```powershell
py -m uv run uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/console/>. Relevant endpoints include:

- `POST /govern/run`
- `GET /govern/pending`
- `POST /govern/pending/{record_id}/approve`
- `POST /govern/pending/{record_id}/reject`
- `GET /govern/audit`
- `GET /govern/audit/blocked`

### Recruiter-facing static showcase

The Astro/Tailwind site is snapshot-first and can be built without provider access:

```powershell
cd frontend
npm ci
npm run build
```

The current site uses the seven-section interview narrative: Hero, Five
Questions, Governed Runtime, Reliability Turn, Q5 Decision Frontier,
Evaluation Infrastructure, and Evidence Ledger. Its Q1–Q5 data contracts are
generated from the canonical Claim registry.

Generated recruiting data:

- `frontend/src/data/questions.json` — complete Q1–Q5 question coverage.
- `frontend/src/data/headline-results.json` — scoped headline candidates and limitations.
- `frontend/src/data/decision-frontier.json` — Grammar / Controlled prose / Open semantics / Unsafe contract.
- `frontend/src/data/q5-evidence.json` — Q5 evidence ledger.
- `frontend/src/data/engineering-signals.json` — engineering/reliability signals.

Every generated record includes a claim ID, tracked artifact, artifact SHA-256, run ID, evidence commit, evidence mode, scope, and headline eligibility.

## Three-minute narrative

The exact timed, claim-bounded version is
`docs/THREE_MINUTE_DEMO_SCRIPT.md`. The outline below is only a navigation
summary.

1. Start with Q1: fail-closed answers make the safety/coverage trade-off explicit.
2. Move to Q3/Q4: the trust boundary reaches side effects, and a weak selection result is corrected without relaxing the gate.
3. Show the runtime console: unauthorized and under-evidenced actions fail closed before the sink.
4. End with Q5: the runtime worked, but the intended LLM-value benchmark collapsed under deterministic challengers; the project closed the track instead of manufacturing a win.
5. Open `docs/Q5_CLAIM_MATRIX.md` to show the hash-bound evidence behind the public wording.

## Honest boundaries

- Structural citation validity is not the same as human semantic support audit.
- Q4 is a disclosed second-run result over frozen `ops_test`, the same thin synthetic corpus surface, and repaired queries—not a pristine one-shot holdout or universal controller guarantee.
- `evidence_mode=real` means actual configured provider/embedding/reranker execution; it does not mean production traffic, customer data, or a real customer incident.
- Mock, synthetic, replay, and offline-control evidence are labeled and cannot masquerade as real-run evidence.
- Q5 efficiency does not imply Q5 semantic value.
- The controlled-prose closure says nothing about open-world language understanding.
- Historical plans to create `q5_test`, enter K1, run confirmatory providers,
  create Boundary G, or publish a Q5 product release are superseded. The exact
  annotated tag `agent-reliability-lab-q5-closed-20260717` is a non-product
  research marker; it does not authorize `v4.0`.

## Verification

Final local-archive regression: `974 passed, 3 skipped, 23 warnings`. The detached
clean clone passed three consecutive Lighthouse performance runs at or above
`90`, accessibility `100/100/100`, Playwright
`55 passed / 14 conditionally skipped`, and release gates `6/6`. Exact per-run
performance scores are receipt-owned. Verify the canonical release envelope
and generated claims with:

```powershell
py -m uv run --frozen python scripts/build_release_manifest.py verify
py -m uv run --frozen python scripts/build_public_claims.py --check
py -m uv run --frozen python scripts/check_claim_drift.py
```

For detailed evidence, use `docs/EVALUATION_REPORT.md`, `docs/FAILURE_ANALYSIS.md`, `docs/Q5_FINAL_REPORT.md`, and `data/claims/claim_registry.json`.

For handoff and maintenance authority, use
`docs/PROJECT_ARCHIVE_AND_MAINTENANCE.md`. The active envelope is
`data/releases/release_manifest_v2.json`; V1 is retained as the pre-archive
historical envelope.
