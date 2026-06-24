---
doc_id: nc-healthcheck
title: Northstar Service Healthcheck
doc_type: api_spec
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

# Northstar Service Healthcheck

## Current Rule

The service liveness probe path is `GET /healthz`, which returns 200 when the service is ready.
