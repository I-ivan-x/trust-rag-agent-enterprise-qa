---
doc_id: sop-api-deprecation-checks
title: Kubernetes API Deprecation Check SOP
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
  - active/001-reference-using-api-deprecation-policy.md
  - active/002-reference-using-api-deprecation-guide.md
  - active/012-concepts-services-networking-endpoint-slices.md
  - active/013-concepts-services-networking-service.md
policy_ref:
corpus_source: public_external
source_origin: generated
source_license_note: Seeded overlay corpus snippet for Q3 action-governance evaluation; synthetic scenario, not upstream Kubernetes documentation.
hard_negative_group_id:
metadata_origin: seeded_overlay
source_url:
---

# Kubernetes API Deprecation Check SOP

Use this seeded checklist when a runbook names Kubernetes APIs that may have changed across releases. Verify policy/v1beta1 PodDisruptionBudget usage against the Kubernetes deprecation guide before approving a 1.25 or later procedure.

For service discovery procedures, prefer EndpointSlice evidence when a runbook still directs operators to read Endpoints directly. Endpoints may remain visible, but EndpointSlice is the modern API surface for scalable service discovery guidance.
