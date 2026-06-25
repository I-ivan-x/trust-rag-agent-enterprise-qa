---
doc_id: sop-pod-security-violations
title: Pod Security Violation Triage SOP
doc_type: deployment_guide
status: active
version: q3-p5-seeded-overlay-v1
created_at: 2026-06-24
updated_at: 2026-06-24
effective_date: 2026-06-24
owner_team: Security Engineering
department: Security
access_level: restricted
allowed_roles:
- admin
tags:
- kubernetes
- config_violation
- seeded_overlay
language: en
supersedes_doc_id:
superseded_by:
conflict_group_id:
is_authoritative: false
overlay_relation_note:
  type: violates_policy
  target_doc_id: sop-pod-security-violations
  policy_doc_id: policy-restricted-pod-security
policy_ref: policy-restricted-pod-security
corpus_source: public_external
source_origin: generated
source_license_note: Seeded overlay corpus snippet for Q3 action-governance evaluation; synthetic scenario, not upstream Kubernetes documentation.
hard_negative_group_id:
metadata_origin: seeded_overlay
source_url:
---

# Pod Security Violation Triage SOP

Flag a configuration violation when a deployment in a restricted namespace sets `securityContext.privileged=true`. The evidence should be paired with the restricted Pod Security Standards anchor and the namespace label enforcement guidance.

Flag a configuration violation when a pod in a baseline namespace requests `hostNetwork=true` and no approved exception is present. Use the securityContext and Pod Security Standards anchors to prepare a remediation ticket.
