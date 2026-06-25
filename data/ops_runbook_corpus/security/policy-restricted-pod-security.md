---
doc_id: policy-restricted-pod-security
title: Restricted Namespace Pod Security Policy Overlay
doc_type: security_policy
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
is_authoritative: true
overlay_relation_note:
  type: policy_overlay
  anchor_docs:
  - security/004-concepts-security-pod-security-standards.md
  - security/006-tasks-configure-pod-container-enforce-standards-namespace-labels.md
policy_ref: policy-restricted-pod-security
corpus_source: public_external
source_origin: generated
source_license_note: Seeded overlay corpus snippet for Q3 action-governance evaluation; synthetic scenario, not upstream Kubernetes documentation.
hard_negative_group_id:
metadata_origin: seeded_overlay
source_url:
---

# Restricted Namespace Pod Security Policy Overlay

In namespaces labeled for the restricted Pod Security Standard, workloads must not request privileged containers. Workloads also must not enable hostNetwork unless a Security Engineering exception is recorded outside this seeded overlay.

When evidence shows `securityContext.privileged=true` in a restricted namespace, or `hostNetwork=true` in a baseline namespace without an exception, open a remediation ticket for an authorized admin workflow.
