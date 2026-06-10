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
language: en
source_path: data/sample_corpus/meeting_notes/auth_token_lifetime_decision.md
supersedes_doc_id: null
superseded_by: null
conflict_group_id: auth-token-lifetime
is_authoritative: false
corpus_source: synthetic_fixture
source_origin: generated
source_license_note: Week 0 synthetic fixture for Northstar Cloud; functional regression only, not for headline metrics.
hard_negative_group_id: null
metadata_origin: native
---

# Auth Token Lifetime Decision Notes

## Decision

The team agreed to keep the access token lifetime at 60 minutes to reduce
re-login friction during the v2 migration.

### Open Item

Security will revisit the 60-minute setting next quarter. These notes have not
been reconciled with the v2 API spec, which currently states 30 minutes.
