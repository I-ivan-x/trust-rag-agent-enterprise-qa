# Agent Reliability Lab frontend

**Governed Runtime, Evaluation Harness, and Decision Frontier for Tool-Using Agents**

Static Astro showcase for the governed runtime, evaluation infrastructure, and
Q5 decision frontier. TrustRAG remains the legacy codename in reproducibility
artifacts; the public project name is Agent Reliability Lab.

## Development

Node.js `>=22.19.0` and npm `>=10.9.0` are required. CI and `.nvmrc` use Node
22.19.0. The site remains a static Astro build: no SSR, server islands, remote
image service, or runtime model/provider call.

```bash
cd frontend
npm ci
npm run dev
npm run build
npm run test:e2e
```

Dependency audit details and the remaining Lighthouse-only moderate advisory are
recorded in [`DEPENDENCY_SECURITY.md`](./DEPENDENCY_SECURITY.md).

## Public data

The Q1–Q5 narrative is generated from `data/claims/claim_registry.json`:

- `src/data/questions.json`
- `src/data/headline-results.json`
- `src/data/decision-frontier.json`
- `src/data/q5-evidence.json`
- `src/data/engineering-signals.json`

Rebuild and verify them from the repository root:

```bash
python scripts/build_public_claims.py
python scripts/build_public_claims.py --check
python scripts/check_claim_drift.py
```

The control-room UI reads `src/data/control-room-trajectory.json`. It is a
runtime-only projection of the committed Q4 `trajectories.json` blob and excludes
gold/correctness fields. Its builder verifies source path, blob SHA-256, run ID,
execution commit, artifact commit, and real mode:

```bash
python scripts/build_control_room_snapshot.py
python scripts/build_control_room_snapshot.py --check
```

`scripts/build_showcase_snapshots.py` remains only as the historical Q4 source
reproducer. The public page does not read `trajectories.json` directly.

## Information architecture

The page contains exactly seven major sections:

1. Hero
2. Five Questions
3. Governed Runtime
4. Reliability Turn
5. Q5 Decision Frontier
6. Evaluation Infrastructure
7. Evidence Ledger

`AgentControlRoom` composes the compact `Pipeline` and `TrajectoryPlayer`.
`DecisionFrontier` provides keyboard-operable segment/state tabs with a complete
no-JavaScript fallback. `EvidenceLedger` exposes every positive, negative, and
not-evaluated claim with source lineage.

## Frontend acceptance

Playwright covers 1440×900, 1280×720, and 390×844. Layout measurement and local
screenshots are produced by:

```bash
node scripts/measure-layout.mjs <url> <commit> [output.json] [width] [height]
node scripts/capture-viewports.mjs <url> [output-directory]
```

The acceptance subset checks the seven-section contract, Q5 position, overflow,
keyboard/focus behavior, reduced motion, no-JavaScript conclusions, and claim
reverse linkage. Lighthouse runs against the same static build.
