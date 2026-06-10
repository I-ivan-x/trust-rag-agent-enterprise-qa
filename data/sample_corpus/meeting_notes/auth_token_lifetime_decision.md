---
doc_id: doc-meeting-auth-token-lifetime-decision
title: Auth Token Lifetime Decision Notes
doc_type: meeting_notes
status: active
version: v1
created_at: 2026-03-15
updated_at: 2026-03-16
effective_date: 2026-04-01
owner_team: Identity Platform
department: Engineering
access_level: internal
allowed_roles:
  - employee
  - engineer
  - product_manager
tags:
  - auth
  - meeting
  - decision
language: zh-CN
source_path: data/sample_corpus/meeting_notes/auth_token_lifetime_decision.md
supersedes_doc_id: null
superseded_by: null
conflict_group_id: auth-token-lifetime
is_authoritative: false
corpus_source: synthetic_fixture
source_origin: generated
source_license_note: Week 0 synthetic fixture; not for headline metrics.
hard_negative_group_id: null
metadata_origin: native
---

# Auth Token Lifetime Decision Notes

## Decision

The team agreed to move from a 60-minute token lifetime to 30 minutes for v2.

### Rationale

The shorter lifetime reduces exposure after credential leakage and aligns with
the v2 rollout plan.

