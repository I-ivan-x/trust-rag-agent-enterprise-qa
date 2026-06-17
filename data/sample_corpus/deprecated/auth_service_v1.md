---
doc_id: doc-api-auth-service-v1
title: Auth Service API v1
doc_type: api_spec
status: deprecated
version: v1
created_at: 2025-02-01
updated_at: 2026-03-01
effective_date: 2025-03-01
owner_team: Identity Platform
department: Engineering
access_level: internal
allowed_roles:
  - employee
  - engineer
tags:
  - auth
  - api
  - deprecated
language: en
source_path: data/sample_corpus/deprecated/auth_service_v1.md
supersedes_doc_id: null
superseded_by: doc-api-auth-service-v2
conflict_group_id: auth-token-lifetime
is_authoritative: false
corpus_source: synthetic_fixture
source_origin: generated
source_license_note: Week 0 synthetic fixture for Northstar Cloud; functional regression only, not for headline metrics.
hard_negative_group_id: null
metadata_origin: native
---

# Auth Service API v1

## Access Token Lifetime

In v1 the access token lifetime was 60 minutes.

### Deprecation Notice

This version is deprecated and is retained only to test stale-evidence handling.
Use Auth Service API v2 for the current behavior.

## Legacy Token Rate Limits

In v1 the token endpoint allowed 10 refresh token requests per minute per
client. These v1 token rate limits are deprecated and must not be used for
current enforcement.
