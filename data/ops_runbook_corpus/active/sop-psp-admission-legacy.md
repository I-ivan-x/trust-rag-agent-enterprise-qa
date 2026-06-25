---
doc_id: sop-psp-admission-legacy
title: PSP Admission Legacy Runbook
doc_type: deployment_guide
status: active
version: q3-p5-seeded-overlay-v1
created_at: 2026-06-24
updated_at: 2026-06-24
effective_date: 2026-06-24
owner_team: Platform Operations
department: Infrastructure
access_level: internal
allowed_roles:
- admin
- editor
tags:
- kubernetes
- stale_procedure
- seeded_overlay
language: en
supersedes_doc_id:
superseded_by:
conflict_group_id:
is_authoritative: false
overlay_relation_note:
  type: stale_procedure
  anchor_docs:
  - deprecated/021-concepts-security-pod-security-policy.md
  - active/003-concepts-security-pod-security-admission.md
policy_ref:
corpus_source: public_external
source_origin: generated
source_license_note: Seeded overlay corpus snippet for Q3 action-governance evaluation; synthetic scenario, not upstream Kubernetes documentation.
hard_negative_group_id:
metadata_origin: seeded_overlay
source_url:
---

# PSP Admission Legacy Runbook

This seeded SOP models an internal page that still mentions PodSecurityPolicy admission as a gate for pods. Treat any step that relies on PSP admission as legacy guidance. Current remediation should compare the legacy PSP material with Kubernetes Pod Security Admission and Pod Security Standards migration guidance.

Operators may flag this SOP as stale when the retrieved evidence includes the PSP source and the current PSA replacement guidance.
