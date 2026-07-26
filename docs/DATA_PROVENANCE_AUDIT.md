# Data Provenance Audit

## Scope

This audit covers every Git-tracked top-level directory under `data/`.
Ignored indexes, generated chunks, local traces, bulk run output, and frontend
runtime reports are not publication inputs. The machine-readable source of
truth is `data/public_repository/audit_registry_v1.json`.

## Tracked data inventory

| Root | Source type | Redistribution status |
| --- | --- | --- |
| `data/action_store/` | Synthetic | Project-authored fixture |
| `data/agent_residual_corpus/` | Project-authored, synthetic | Project-authored fixture |
| `data/citation_audit/` | Project-authored, immutable evidence | Evidence-only |
| `data/claims/` | Project-authored, immutable evidence | Evidence-only |
| `data/eval_baselines/` | Project-authored, immutable evidence | Evidence-only |
| `data/eval_runs/` | Historical immutable artifact | Evidence-only |
| `data/gold_eval/` | Project-authored, synthetic | Project-authored labels |
| `data/hard_negative_corpus/` | FastAPI public text plus local pairing | Upstream MIT with attribution |
| `data/ops_runbook_corpus/` | Kubernetes public text plus local SOP/overlay | Upstream CC BY 4.0 with attribution |
| `data/public_corpus/` | FastAPI public documentation | Upstream MIT with attribution |
| `data/public_repository/` | Project-authored audit artifacts | Evidence-only |
| `data/q5/` | Project-authored, synthetic, archived dev evidence | Evidence-only |
| `data/q5_frontier/` | Project-authored, synthetic, immutable evidence | Evidence-only |
| `data/redteam_adjudication/` | Project-authored labels | Evidence-only |
| `data/redteam_corpus/` | Project-authored, synthetic | Project-authored fixture |
| `data/releases/` | Project-authored schemas, manifests, receipts | Evidence-only |
| `data/sample_corpus/` | Project-authored Northstar Cloud fixtures | Project-authored fixture |
| `data/showcase/` | Project-authored, synthetic | Demonstration-only fixture |

Every row has at least one tracked provenance anchor. Missing, extra, or
unclassified data roots fail the repository gate.

## Public third-party material

### FastAPI

`data/public_corpus/` contains attributed FastAPI documentation sourced from
the public `fastapi/fastapi` repository. The hard-negative corpus reuses
attributed pages and adds project-authored pair metadata. Redistribution
follows the upstream MIT license. Synthetic access/state overlays are marked
as local metadata and do not claim to be upstream history.

### Kubernetes

`data/ops_runbook_corpus/` combines attributed Kubernetes documentation under
CC BY 4.0 with project-authored SOPs and controlled policy overlays. The
manifest preserves source URLs and license notes. Local overlays do not alter
the upstream prose or grant additional rights over it.

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

The owner has not selected Apache-2.0 or MIT, so no repository-wide license is
asserted. A future project license must not silently relicense FastAPI,
Kubernetes, or immutable third-party-derived evidence. Source-level
attribution and upstream terms continue to apply independently.
