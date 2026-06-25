---
doc_id: policy-rbac-readonly-audit-view
title: Audit Binding Allowlist
doc_type: security_policy
status: active
version: q3-p5-seeded-overlay-v1
created_at: 2026-06-24
updated_at: 2026-06-24
effective_date: 2026-06-24
owner_team: Security Engineering
department: Security
access_level: internal
allowed_roles:
- admin
- editor
tags:
- kubernetes
- no_op
- seeded_overlay
language: en
supersedes_doc_id:
superseded_by:
conflict_group_id:
is_authoritative: true
overlay_relation_note:
  type: policy_overlay
  outcome: allowed
  anchor_docs:
  - security/010-concepts-security-rbac-good-practices.md
policy_ref:
corpus_source: public_external
source_origin: generated
source_license_note: Seeded overlay corpus snippet for Q3 action-governance evaluation; synthetic scenario, not upstream Kubernetes documentation.
hard_negative_group_id:
metadata_origin: seeded_overlay
source_url:
---

# Audit Binding Allowlist

The read-only audit group may be bound to the Kubernetes `view` ClusterRole when the request is limited to inspection and does not include secrets, workload creation, or privileged escalation paths.

This seeded policy overlay is a no-op sample: do not open a remediation ticket or send an alert when evidence only supports the allowed read-only `view` binding.
