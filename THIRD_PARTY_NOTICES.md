# Third-party notices

Agent Reliability Lab is a multi-license source repository.

The root Apache License 2.0 applies to project-authored code, documentation,
configuration, synthetic data, labels, overlays, and original metadata unless a
file or directory says otherwise. It does not relicense third-party material.

## Historical tag notice

The immutable product tags through `v3.0-q4-reliability` predate the commit that
added the root `LICENSE`, this notice, and the local third-party license copies.
The Owner's Apache-2.0 grant in current `main` covers project-authored material
retained in that repository history, but a standalone archive of an older tag
does not contain the governing texts. Anyone using such an archive must also
consult the current `LICENSE`, this notice, and `LICENSES/`; FastAPI and
Kubernetes material always remains under the upstream terms listed below.
Historical tags must not be moved merely to insert these files.

## FastAPI documentation

- Paths: `data/public_corpus/` and the copied source pages under
  `data/hard_negative_corpus/`.
- Upstream: <https://github.com/fastapi/fastapi>
- License: MIT.
- Copyright: Copyright (c) 2018 Sebastián Ramírez.
- Local license copy: `LICENSES/FASTAPI-MIT.txt`.
- Modification notice: the source excerpts are retained as collected;
  project-authored manifests, pairing metadata, labels, and evaluation
  structure are separate additions.
- Exact upstream commit: unknown. Historical source URLs use the moving
  `master` branch, so this repository does not claim a recoverable upstream
  revision.

## Kubernetes documentation

- Path: the 21 upstream documents under `data/ops_runbook_corpus/`.
  Project-authored SOP overlays in that directory are not Kubernetes content.
- Upstream: <https://github.com/kubernetes/website>
- License: Creative Commons Attribution 4.0 International
  (CC BY 4.0; SPDX `CC-BY-4.0`).
- Attribution: Kubernetes Authors / Kubernetes website contributors.
- Local license copy: `LICENSES/KUBERNETES-CC-BY-4.0.txt`.
- Modification notice: the upstream prose is retained as collected; local
  manifests and policy overlays are separate additions.
- Exact upstream commit: unknown. Historical source URLs use the moving `main`
  branch, so this repository does not claim a recoverable upstream revision.

The 21 historical Kubernetes files contain an inaccurate local `source_path`
front-matter prefix. The authoritative runtime manifest at
`data/ops_runbook_corpus/public_corpus_manifest.jsonl` records the correct local
paths and source URLs. The frozen source files were not silently rewritten.

## Canonical evidence is not a copyright restriction

Some project-authored and third-party-backed files are marked as canonical,
immutable, or byte-frozen for scientific lineage. That label is an evidence
validity rule only. Downstream modification remains permitted under the
applicable license; a modified copy simply is not canonical evidence for this
project.

Direct and transitive software dependencies retain their own licenses. The
audited direct-dependency inventory is recorded in
`data/public_repository/dependency_audit_v1.json`. This source release does not
redistribute `node_modules`, Python environments, or the transitive `libvips`
binary; a future binary distribution requires a separate license audit.
