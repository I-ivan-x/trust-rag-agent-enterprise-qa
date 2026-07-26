# Public Repository Audit

## Decision

Agent Reliability Lab is suitable for a public source repository at the audited
commit, subject to the owner choosing a repository license. The audit is
fail-closed and is enforced by `scripts/verify_public_repository.py`.

The latest stable release remains `v3.0-q4-reliability`. The pending research
milestone is named `q5-scoped-negative-research-closure`; this audit does not
create a tag or release.

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
| Q5 boundary | `q5_test` is absent. No Boundary G, K1 data, provider run, tag, or release is created. | Repository and release verifier |

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

The frontend production dependency audit records zero vulnerabilities. The
development tree retains 17 moderate entries through the Lighthouse-only
`@sentry/node` → OpenTelemetry chain for `GHSA-8988-4f7v-96qf`. It is absent
from the static production bundle, high and critical findings remain zero, and
this batch does not perform a breaking downgrade. The detailed reachability
record remains in `frontend/DEPENDENCY_SECURITY.md`.

The Python review is offline because this batch permits no external advisory
request. It records no known direct-runtime advisory in the repository, but it
does not claim that an offline lock inspection replaces a current OSV or
GitHub Advisory Database query before a later release.

## License recommendation for the owner

No `LICENSE` file was created.

- **Apache-2.0** is the stronger fit when the owner wants an explicit patent
  grant and clearer notice obligations for a governance/runtime project.
- **MIT** is the shortest and most familiar option for interview and portfolio
  reuse, with minimal redistribution conditions, but without Apache-2.0's
  explicit patent language.

Either choice concerns project-authored code and data only. It cannot replace
the upstream MIT terms for FastAPI documentation, CC BY 4.0 attribution for
Kubernetes documentation, or the provenance restrictions on immutable
evaluation artifacts. The owner must make the final choice.

## Residual risks

- The offline Python advisory statement can age after this manifest is cut.
- Lighthouse's development-only moderate chain remains accepted, not fixed.
- Historical artifacts are intentionally retained for reproducibility; their
  public meaning must continue to come through the Claim registry rather than
  isolated raw fields.
- A future change to dependency locks, data roots, public brand surfaces, or
  legacy-codename locations invalidates this audit until the registry is
  updated and reverified.
