# Public Repository Audit

## Decision

Agent Reliability Lab is suitable for a public source repository at the audited
commit. Apache-2.0 is selected for project-authored material; third-party
material remains under its upstream license. The active machine-readable
contract is `data/public_repository/audit_registry_v2.json`, and the fail-closed
gate is `scripts/verify_public_repository.py`.

The latest stable product release remains `v3.0-q4-reliability`. The only Q5
tag authorized by closure is the annotated, non-product research marker
`agent-reliability-lab-q5-closed-20260717`; it does not create a GitHub Release
or `v4.0`.

## Publication checks

| Area | Result | Enforcement |
| --- | --- | --- |
| Secrets and credentials | No real token, private key, credential URL, or access key is accepted on a non-fixture path. | High-confidence tracked-text scan |
| PII and private endpoints | No undeclared email, SSN-shaped value, CN mobile number, or private IPv4 address is accepted outside declared synthetic/upstream fixtures. | Tracked-text scan with explicit fixture roots |
| Git boundary | Ignored runtime output, indexes, generated chunks, frontend build output, and raw Lighthouse reports must not be tracked. | `git ls-files -ci` and forbidden-prefix closure |
| Claims | Every formal Claim surface remains independent of `data/showcase/`. | Claim-source and generated-surface scan |
| Brand | Current public surfaces use **Agent Reliability Lab**. | Exact public-surface registry |
| Legacy codename | **TrustRAG** is limited to declared historical artifacts, internal identifiers, and three explicit public explanations of the rename. | Path allowlist |
| Image accessibility | HTML/Astro images require `alt`; Markdown images cannot use an empty label. | Source scan |
| Q5 boundary | `q5_test` is absent. No Boundary G, K1 data, provider run, product release, or `v4.0` is created; the one exact annotated research marker is separately constrained. | Repository and release verifier |
| Project license | Root Apache-2.0 text, package metadata, notices, exclusions, and SHA-256 values agree. | V2 registry plus mutation tests |
| Third-party material | FastAPI MIT and Kubernetes CC BY 4.0 scopes, attribution, license references, and hashes remain explicit. | Structured third-party inventory |

Synthetic red-team files intentionally contain credential-shaped canaries and
public upstream documentation contains fictional example identities. Those
directories are declared fixtures or attributed third-party sources. The
exception is path-scoped; moving the same text into a normal document fails the
gate.

The seven Boundary F addendum files are the only declared exception to the
general `data/eval_runs/*` ignore rule. They were deliberately force-added as
immutable release evidence; any missing or additional tracked/ignored path
fails the closure check.

The Python distribution name remains a legacy internal identifier for
compatibility, while its description carries the current public subtitle. The
frontend package metadata uses `agent-reliability-lab-showcase`.

## Dependency audit

The dependency record is bound to `uv.lock` and
`frontend/package-lock.json`. Direct Python and npm dependencies have an
explicit license row. Current direct dependencies use permissive licenses such
as MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, and ISC.

The frontend production and development dependency audits record zero known
vulnerabilities after the non-breaking Lighthouse 13.4.0 → 13.4.1 patch removed
the former `@sentry/node` → OpenTelemetry/minimatch advisory chain. High and
critical findings remain release-blocking. The lock-bound record and prior
reachability history remain in `frontend/DEPENDENCY_SECURITY.md`.

The Python review is offline because this batch permits no external advisory
request. It records no known direct-runtime advisory in the repository, but it
does not claim that an offline lock inspection replaces a current OSV or
GitHub Advisory Database query before a later release.

## Repository-license decision

The Owner decision is closed: project-authored material uses **Apache-2.0**.
The repository gate verifies:

- root `LICENSE` content and SHA-256;
- `pyproject.toml`, `frontend/package.json`, and package-lock metadata;
- `THIRD_PARTY_NOTICES.md`;
- the FastAPI MIT and Kubernetes CC BY 4.0 license references; and
- exact third-party path exclusions from the root project license.

Apache-2.0 covers project-authored code, documentation, configuration,
synthetic data, labels, overlays, and original metadata. It does not relicense
FastAPI source pages under `data/public_corpus/` or
`data/hard_negative_corpus/`, nor the 21 Kubernetes documents under
`data/ops_runbook_corpus/`. Those remain MIT and CC BY 4.0 respectively.

Canonical or byte-frozen evidence is a scientific-lineage rule, not a
copyright restriction. Downstream modification remains allowed under the
applicable license; a changed copy simply ceases to be canonical evidence for
this project.

## Residual risks

- The offline Python advisory statement can age after this manifest is cut.
- Advisory data can change after the tracked audit and must be refreshed before
  any later release or dependency-lock change.
- Historical artifacts are intentionally retained for reproducibility; their
  public meaning must continue to come through the Claim registry rather than
  isolated raw fields.
- Historical corpus URLs use moving `master`/`main` branches, so exact upstream
  revisions are recorded as `unknown` rather than invented.
- The 21 frozen Kubernetes files contain an inaccurate local `source_path`
  front-matter prefix. The correct runtime paths and source URLs are in
  `data/ops_runbook_corpus/public_corpus_manifest.jsonl`; the historical files
  were not silently rewritten.
- This source release does not redistribute environments, `node_modules`, or
  transitive `libvips` binaries. A future binary distribution needs a separate
  license audit.
- A future change to dependency locks, data roots, public brand surfaces, or
  legacy-codename locations invalidates this audit until the registry is
  updated and reverified.
