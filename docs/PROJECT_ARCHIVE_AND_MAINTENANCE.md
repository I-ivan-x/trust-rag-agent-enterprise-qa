# Agent Reliability Lab — Project Archive and Maintenance Policy

Status: local archival closure

Effective date: 2026-07-27

Maintenance mode: security, reproducibility, factual correction, and compatibility only

## 1. Closure statement

Agent Reliability Lab reached **local archival closure** on 2026-07-27. The
Q1–Q5 implementation, scoped research conclusions, public Claim registry,
frontend acceptance evidence, public-repository audit, and clean-clone release
envelope are present in the local Git history.

This status does **not** mean that publication has completed:

- `origin/main` has not yet been advanced to the archival history;
- the archival branch has not yet passed CI on the remote repository;
- the local Q3 and Q4 tags have not yet been confirmed on the remote;
- the Q5 research milestone tag is a local-only archival marker and has not
  been pushed; and
- the static showcase has no audited production deployment in this closure.

Until the remote publication conditions in §10 pass, public wording must say
“locally archived and reproducible,” not “published,” “deployed,” or “remote-CI
verified.”

## 2. Sources of truth

When documents disagree, use this precedence order:

1. `data/claims/claim_registry.json` defines current public Claim status,
   evidence scope, eligibility, limitations, and source artifacts.
2. `data/releases/release_manifest_v2.json` and its clean-clone receipt define
   which repository snapshot was mechanically reproduced.
3. `data/public_repository/audit_registry_v2.json` defines publication,
   provenance, dependency, license, and tracked-data boundaries.
4. This document defines archive lifecycle and maintenance authority.
5. Generated Claim views are projections of the registry, not independent
   sources.
6. Historical plans, specifications, reports, run artifacts, and tag messages
   retain their period meaning but do not override current policy.

The canonical evidence package proves that a named Claim was valid at its
recorded commit and scope. It does **not** prohibit future maintenance of source
code, documentation, dependencies, or presentation. A later change invalidates
only the assumption that the old manifest describes the new tree; it does not
erase the old evidence.

## 3. Frozen research and release boundaries

The following boundaries remain frozen:

- Q5 overall status is `scoped_negative_complete`.
- `controlled_prose_track=closed`.
- K1 is not approved.
- Boundary G is not allowed.
- New K1 data is not allowed.
- `q5_test` remains absent and must not be created or read.
- No confirmatory provider run is authorized under the closed Q5 protocol.
- Open-world LLM value remains `not_evaluated`.
- Historical Boundary A–F artifacts and the Boundary F addendum remain
  sequential evidence; corrections use a new addendum rather than rewriting
  prior bytes.
- `v3.0-q4-reliability` remains the latest stable **product** release.
- No `v4.0` product release is created by Q5 closure.

Exactly one non-product research milestone tag is allowed:

`agent-reliability-lab-q5-closed-20260717`

It must be an annotated tag whose message states the scoped-negative
conclusion. It is not a semantic-version product tag, does not make Q5 a
product release, and must not be accompanied by a `v4.0` tag or a product
release object. This exact exception supersedes older broad wording that said
no Q5 tag of any kind; all other Q5 tags remain unauthorized.

## 4. Maintenance scope

The repository is maintenance-only after archival closure.

| Change class | Archived mode | Required treatment |
| --- | --- | --- |
| Security remediation | Allowed | Preserve fail-closed behavior; run affected tests, public audit, and release verification |
| Dependency or supported-runtime compatibility | Allowed | Refresh lockfiles deliberately, dependency audit, clean-clone receipt, and manifest |
| CI, reproducibility, or cross-platform repair | Allowed | Add regression coverage; do not weaken gates or thresholds to obtain green status |
| Documentation, accessibility, or presentation correction | Allowed | Keep Claims registry-first; refresh bound frontend evidence when output changes |
| Claim wording, limitation, or status correction | Allowed through §7 only | Bind tracked evidence and regenerate every derived surface |
| Provenance, attribution, or license correction | Allowed and mandatory when discovered | Fail publication closed until the audit is current |
| New product capability or new experimental conclusion | Not allowed in archived mode | Requires formal unfreezing under §9 |
| Historical artifact rewrite, tag movement, or evidence deletion | Prohibited | Add a superseding artifact or addendum instead |

Maintenance must not silently expand a Claim from its frozen scope, relabel
mock or synthetic evidence as real, or convert an unevaluated question into a
positive or negative conclusion.

## 5. Canonical evidence change rules

Repository files fall into three lifecycle classes:

1. **Historical evidence** — run artifacts, frozen reports, signed receipts,
   and existing tags are append-only. A discovered error is documented with a
   correction or addendum that preserves the original lineage.
2. **Current truth surfaces** — the Claim registry, presentation catalog,
   public audit registry, schemas, and release envelope may change through
   their generators and verifiers. Each accepted change creates a new,
   reviewable Git state; it never retroactively changes what an older commit
   demonstrated.
3. **Maintainable implementation** — code, tests, CI, documentation,
   dependencies, and the frontend may be repaired. If the change touches an
   artifact bound by the current manifest, the manifest and clean-clone
   receipt must be refreshed before the new state is called reproducible.

Never hand-edit a generated Claim view. Never force-move a tag. Never amend or
rebase a published evidence commit.

## 6. Maintenance cadence

Cadence is a verification schedule, not a response-time or support SLA.
Maintenance is best-effort unless the Owner explicitly reactivates the
project.

### Per change

- Run locked Python installation, Ruff, the relevant tests, and full pytest
  before an archive-envelope or publication change.
- Run Claim build/check/drift, showcase isolation, public-repository audit,
  frontend artifact verification, and canonical manifest verification.
- Treat high or critical dependency advisories, secret/PII findings,
  unclassified data roots, unknown Claim sources, and manifest drift as
  release-blocking.
- Refresh every receipt or audit whose bound bytes, lock hash, commit, or
  generated surface changed.

### Monthly while the project is publicly showcased

- Review Python and npm advisories against the tracked lockfiles.
- Review repository-host security alerts and dependency update notices.
- Re-run secret/PII, legacy-brand, showcase-isolation, and data-root closure
  checks.
- Confirm that the public page and README still use generated Claim data and
  have not acquired manually copied headline numbers.
- Record a commit or issue when state changes; a no-op review does not require
  artificial repository churn.

### Quarterly, and before every new tag or public release

- Run the full clean-clone procedure on supported runtimes.
- Recheck every tracked data root, source URL, upstream license, attribution,
  and redistribution boundary.
- Run a current online advisory review for both Python and npm dependencies;
  the historical offline Python statement is not sufficient for a new
  release.
- Reconfirm the stable product tag, exact research milestone policy, absence
  of `q5_test`, and zero unauthorized model/evaluation requests.
- Refresh the canonical release receipt and manifest when any bound input has
  changed.

Any uncertain provenance, material Claim contradiction, or high/critical
security finding temporarily blocks publication of the affected surface until
it is resolved or explicitly withdrawn.

## 7. Claim registry-first change process

Every public Claim change follows this order:

1. Identify the exact Claim ID and whether the change affects wording, scope,
   status, metrics, eligibility, evidence mode, or limitation.
2. Add or identify a Git-tracked source artifact with run ID, evidence commit,
   source hash, real/mock/synthetic classification, and claim scope.
3. Verify that the evidence commit is in the retained ancestry and that the
   artifact is safe for public distribution.
4. Edit `data/claims/claim_registry.json` and, when presentation copy changes,
   its canonical presentation catalog. Do not edit generated Markdown or
   frontend JSON directly.
5. Rebuild the generated views and inspect the complete diff.
6. Run Claim schema, lineage, source-import, drift, showcase-isolation, brand,
   and public-repository gates.
7. If the frontend output changed, repeat build, Playwright, screenshots, and
   three-run Lighthouse acceptance.
8. Run detached clean-clone verification and rebuild the release manifest.
9. Obtain Owner review before making a Claim more favorable, broader, or
   headline-eligible.

A status upgrade requires new evidence. A wording cleanup cannot broaden an
old result. A correction that weakens or withdraws a Claim may proceed
immediately once the contradiction is verified, but still requires regenerated
surfaces and a new release envelope.

## 8. Git history and merge policy

Evidence lineage depends on ancestry. Publication must preserve it.

- Advance `main` by fast-forward when possible. A true merge commit that
  retains all parents is acceptable when fast-forward is impossible.
- Do not squash, rebase, or cherry-pick the archival chain into a new history.
- Do not use force-push for `main` or any release/research tag.
- CI that verifies the release manifest must fetch full history and tags; a
  shallow checkout is insufficient for ancestry and annotated-tag checks.
- Existing tags are immutable. Later maintenance receives new commits and, if
  explicitly approved, a new tag; an old tag is never moved.
- Remote publication must preserve the tested commit as an ancestor of the
  published archive-envelope commit.
- The `release_manifest_v2` name identifies the envelope contract family, while
  its exact schema bytes remain Git-snapshot-versioned. A historical tag is
  verified against the schema committed at that tag; later fail-closed
  maintenance may tighten V2 fields without rewriting the historical tag.

These rules apply to publication history, not to disposable local experiments
that are never used as Claim evidence.

## 9. Unfreezing conditions

Archived mode may be lifted only for one of these reasons:

- a confirmed security defect requires a runtime or evidence-contract change;
- the documented clean-clone path no longer reproduces on a supported runtime;
- a public Claim is contradicted by its own evidence or a lineage defect;
- a material license, attribution, or data-provenance defect is discovered; or
- the Owner approves a new research charter with a distinct hypothesis,
  protocol, namespace, budget, success/failure gate, and publication boundary.

A newer model, a desire for a better metric, interview optics, or curiosity
about the two former parser misses is not sufficient.

Unfreezing requires a dated decision record that names affected Claims and
frozen artifacts, a new branch, explicit acceptance criteria, and an updated
manifest strategy. Closed Q5 namespaces are not reused: any future open-world
study receives new dataset, protocol, run, and Claim identifiers. It must not
create the previously withheld `q5_test`, K1, or Boundary G artifacts.

## 10. Archive and publication acceptance

### Local archival closure

Local archival closure requires:

- all intended changes committed and the worktree clean;
- full pytest and Ruff passing under locked dependencies;
- Claim build/check/drift and public-repository audit passing;
- frontend build, Playwright, three-run Lighthouse, accessibility, and
  screenshot hashes passing;
- release gates passing;
- detached no-hardlinks clean clone passing with zero model and evaluation
  external requests at the instrumented application/browser boundary;
- canonical manifest verification passing;
- project license and third-party attribution boundaries mechanically
  verified; and
- `q5_test` absent, K1 false, Boundary G absent, and stable product tag still
  `v3.0-q4-reliability`.

### Remote publication

Remote publication is a separate terminal condition. It requires:

- remote `main` at the intended archive-envelope commit with preserved
  ancestry;
- remote CI green on that commit using full history and tags;
- local and remote `v3.0-q4-reliability` resolving to the same annotated tag;
- the exact annotated research milestone tag remains an immutable archive
  ancestor of the tested commit, with both its annotated tag object and peeled
  target matching the release manifest, and is pushed without creating `v4.0`;
- remote tag and peeled commit verified after push; and
- any deployed showcase URL, if one is later added, built from the same
  reviewed source state and tested independently.

No local test result may be used as evidence that remote CI or deployment
passed.

## 11. Reproduction commands

Run from the repository root in PowerShell.

The clean-clone runner's internal 14-command matrix records portable logical
`uv` commands plus the actual launcher class (`uv` executable or
`python -m uv`). It also records OS, architecture, Python/uv/Node/npm,
Playwright/Chromium, working directory, and offline environment overrides.
Each receipt proves the recorded platform/runtime combination; it is not an
OS-level network attestation or a claim that every platform was tested.
Installer outputs such as `.venv` and `node_modules` are expected ignored
workspace products; the runner separately requires zero tracked or
non-ignored file changes after verification.
On POSIX shells, invoke the same Python scripts with `uv run --frozen python`
instead of the PowerShell `py -m uv` launcher shown below.

### Core and governance verification

```powershell
py -m uv sync --locked --group dev
py -m uv lock --check
py -m uv run --frozen ruff check .
py -m uv run --frozen pytest -ra

py -m uv run --frozen python scripts/build_public_claims.py --check
py -m uv run --frozen python scripts/check_claim_drift.py
py -m uv run --frozen python scripts/build_interview_showcase.py --check
py -m uv run --frozen python scripts/verify_public_repository.py
py -m uv run --frozen python scripts/verify_frontend_closure.py

py -m uv run --frozen python scripts/check_release_gates.py `
  --summary tests/fixtures/release_gates/ci_clean_summary.json `
  --leakage tests/fixtures/release_gates/ci_clean_leakage.json

py -m uv run --frozen python scripts/build_release_manifest.py verify
git diff --check
git status --short
```

### Frontend verification

```powershell
Push-Location frontend
npm ci
npm audit --audit-level=high
npm run build
npm run test:e2e
npm run test:closure-acceptance
Pop-Location
```

### Refresh a changed release envelope

Run this only after committing the exact source state to be tested:

```powershell
py -m uv run --frozen python scripts/verify_release_clean_clone.py `
  --commit HEAD `
  --output data/releases/clean_clone_receipt_v1.json

py -m uv run --frozen python scripts/build_release_manifest.py build `
  --tested-commit HEAD

py -m uv run --frozen python scripts/build_release_manifest.py verify
```

Commit the refreshed receipt and manifest, rerun their verifiers, and require a
clean worktree before publication.

### Research milestone verification

After local archival closure, verify the local marker with:

```powershell
git cat-file -t agent-reliability-lab-q5-closed-20260717
git rev-list -n 1 agent-reliability-lab-q5-closed-20260717
git for-each-ref refs/tags/agent-reliability-lab-q5-closed-20260717 `
  --format="%(objecttype) %(objectname) %(subject)"
git tag --list "v4.0*"
```

Only after explicit publication authorization and green remote CI, verify the
remote marker separately:

```powershell
git ls-remote --tags origin `
  "refs/tags/agent-reliability-lab-q5-closed-20260717*"
```

The first command must report `tag`, the milestone must peel to the recorded
immutable archive ancestor, and the `v4.0*` query must be empty. If publication is later
authorized, the remote reference must match the local tag after it is pushed.
