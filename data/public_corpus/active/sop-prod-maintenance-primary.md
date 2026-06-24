---
doc_id: sop-prod-maintenance-primary
title: Production Maintenance Primary SOP
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
tags:
- kubernetes
- active_active_conflict
- seeded_overlay
language: en
supersedes_doc_id:
superseded_by:
conflict_group_id: q3-prod-maintenance-conflict
is_authoritative: false
overlay_relation_note:
  type: active_active_conflict
  paired_doc_id: sop-prod-maintenance-secondary
policy_ref:
corpus_source: public_external
source_origin: generated
source_license_note: Seeded overlay corpus snippet for Q3 action-governance evaluation; synthetic scenario, not upstream Kubernetes documentation.
hard_negative_group_id:
metadata_origin: seeded_overlay
source_url:
---

# Production Maintenance Primary SOP

For production etcd, take a backup every 6h during the change window. This seeded SOP is active and conflicts with another active maintenance SOP that gives a different backup period.

For cluster upgrades, cordon the node first, then drain it after workload owners acknowledge the maintenance window.
