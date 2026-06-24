---
doc_id: nc-webhook-retry-2026
title: Northstar Webhook Retry Policy 2026
doc_type: deployment_guide
status: active
version: v2
access_level: internal
allowed_roles:
  - employee
corpus_source: agent_residual
source_origin: generated
metadata_origin: native
is_authoritative: true
---

# Northstar Webhook Retry Policy 2026

## Current Rule

When a hook endpoint is down, failed webhook deliveries retry with exponential backoff for up to 24 hours, then drop.
