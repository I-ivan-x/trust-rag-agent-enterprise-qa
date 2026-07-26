# Data Provenance Audit

## Scope

This audit covers every Git-tracked top-level directory under `data/`.
Ignored indexes, generated chunks, local traces, bulk run output, and frontend
runtime reports are not publication inputs. The active machine-readable source
of truth is `data/public_repository/audit_registry_v2.json`; V1 remains a
historical pre-license snapshot.

## Tracked data inventory

| Root | Source type | Redistribution status |
| --- | --- | --- |
| `data/action_store/` | Synthetic | Project-authored fixture |
| `data/agent_residual_corpus/` | Project-authored, synthetic | Project-authored fixture |
| `data/citation_audit/` | Project-authored, canonical evidence | Apache-2.0; canonical copy byte-frozen |
| `data/claims/` | Project-authored, canonical evidence | Apache-2.0; canonical copy byte-frozen |
| `data/eval_baselines/` | Project-authored, canonical evidence | Apache-2.0; canonical copy byte-frozen |
| `data/eval_runs/` | Historical canonical artifact | Apache-2.0; canonical copy byte-frozen |
| `data/gold_eval/` | Project-authored, synthetic | Project-authored labels |
| `data/hard_negative_corpus/` | FastAPI public text plus local pairing | Upstream MIT with attribution |
| `data/ops_runbook_corpus/` | Kubernetes public text plus local SOP/overlay | Upstream CC BY 4.0 with attribution |
| `data/public_corpus/` | FastAPI public documentation | Upstream MIT with attribution |
| `data/public_repository/` | Project-authored audit artifacts | Apache-2.0; canonical copy byte-frozen |
| `data/q5/` | Project-authored, synthetic, archived dev evidence | Apache-2.0; canonical copy byte-frozen |
| `data/q5_frontier/` | Project-authored, synthetic, canonical evidence | Apache-2.0; canonical copy byte-frozen |
| `data/redteam_adjudication/` | Project-authored labels | Apache-2.0; canonical copy byte-frozen |
| `data/redteam_corpus/` | Project-authored, synthetic | Project-authored fixture |
| `data/releases/` | Project-authored schemas, manifests, receipts | Apache-2.0; canonical copy byte-frozen |
| `data/sample_corpus/` | Project-authored Northstar Cloud fixtures | Project-authored fixture |
| `data/showcase/` | Project-authored, synthetic | Demonstration-only fixture |

Every row has at least one tracked provenance anchor. Missing, extra, or
unclassified data roots fail the repository gate.

## Public third-party material

### FastAPI

`data/public_corpus/` contains 40 attributed FastAPI documentation pages
sourced from the public `fastapi/fastapi` repository. The hard-negative corpus
contains 20 pairs / 40 copied pages and adds project-authored pair metadata.
The source pages remain MIT; local metadata is Apache-2.0. Historical URLs use
the moving `master` branch, so the exact upstream commit is explicitly
`unknown`.

### Kubernetes

`data/ops_runbook_corpus/` combines 21 attributed Kubernetes documents under
CC BY 4.0 with nine project-authored SOPs/controlled overlays under
Apache-2.0. Historical URLs use the moving `main` branch, so the exact upstream
commit is explicitly `unknown`.

The 21 frozen upstream files have an inaccurate local `source_path`
front-matter prefix. The authoritative runtime manifest
`data/ops_runbook_corpus/public_corpus_manifest.jsonl` records the correct
local paths and source URLs. The defect is disclosed rather than silently
rewriting the historical corpus.

## Synthetic and project-authored material

Northstar Cloud samples, red-team canaries, Q5 dev/frontier material, the
interview incident, action-store rows, and Gold labels are fictional or
project-authored. They contain no real customer, employee, provider, or
production incident data.

The interview corpus is explicitly:

- `data_mode=synthetic`
- `use=demonstration_only`
- `headline_eligible=false`
- `formal_evaluation=false`
- `model_requests=0`
- `external_requests=0`

The verifier rejects any reference from that corpus into the Claim registry,
generated headline views, Q5 Final Report, Claim Matrix, or Boundary Summary.

## Historical immutable artifacts

Tracked run summaries, Boundary A–F evidence, receipts, claim source snapshots,
and audit labels are retained byte-for-byte to preserve the research timeline.
Their presence does not make every raw field a current public conclusion.
Current conclusions come only from the hash-bound Claim registry and generated
views.

Boundary F remains two sequential layers:

1. the original frozen 30/32 audit evidence; and
2. the later addendum resolving the frozen 32-case scope.

The addendum does not rewrite the original evidence and does not establish
open-world LLM value.

## Repository-license boundary

Apache-2.0 is selected for project-authored material. The repository is still
multi-license: FastAPI pages remain MIT and Kubernetes pages remain CC BY 4.0.
`THIRD_PARTY_NOTICES.md` and `LICENSES/` carry path-specific attribution and
license references.

“Canonical,” “immutable,” and “byte-frozen” express evidence validity at a
recorded commit. They do not add a no-derivatives restriction. Downstream
modification remains permitted under the applicable license, but modified
copies are no longer canonical evidence for this project.
