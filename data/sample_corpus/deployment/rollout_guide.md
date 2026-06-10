---
doc_id: doc-deployment-rollout-guide
title: Auth Service Rollout Guide
doc_type: deployment_guide
status: active
version: v1
created_at: 2026-03-01
updated_at: 2026-03-20
effective_date: 2026-04-01
owner_team: Release Engineering
department: Engineering
access_level: internal
allowed_roles:
  - employee
  - engineer
  - release_manager
tags:
  - deployment
  - rollout
language: en
source_path: data/sample_corpus/deployment/rollout_guide.md
supersedes_doc_id: null
superseded_by: null
conflict_group_id: null
is_authoritative: true
corpus_source: synthetic_fixture
source_origin: generated
source_license_note: Week 0 synthetic fixture for Northstar Cloud; functional regression only, not for headline metrics.
hard_negative_group_id: null
metadata_origin: native
---

# Auth Service Rollout Guide

## Deployment Window

The rollout window for v2 is Tuesday 22:00 to 23:00 local time.

### Rollback Signal

Rollback is required if the login error rate exceeds 2% for five consecutive
minutes.
