---
doc_id: doc-api-auth-service-v2
title: Auth Service API v2
doc_type: api_spec
status: active
version: v2
created_at: 2026-01-10
updated_at: 2026-03-18
effective_date: 2026-04-01
owner_team: Identity Platform
department: Engineering
access_level: internal
allowed_roles:
  - employee
  - engineer
tags:
  - auth
  - api
  - token
language: en
source_path: data/sample_corpus/api/auth_service_v2.md
supersedes_doc_id: doc-api-auth-service-v1
superseded_by: null
conflict_group_id: auth-token-lifetime
is_authoritative: true
corpus_source: synthetic_fixture
source_origin: generated
source_license_note: Week 0 synthetic fixture for Northstar Cloud; functional regression only, not for headline metrics.
hard_negative_group_id: null
metadata_origin: native
---

# Auth Service API v2

## Access Token Lifetime

In v2 the access token lifetime is 30 minutes.

### Refresh Behavior

Clients must refresh before expiry and must not assume the v1 lifetime rules.

## Refresh Token Rate Limit

The refresh token endpoint is limited to 30 requests per minute per client.
Requests above this limit receive an HTTP 429 response.

## Current Token Rate Limits

The active v2 token rate limit is 30 refresh token requests per minute per
client. The v1 token rate limits are no longer in effect.
