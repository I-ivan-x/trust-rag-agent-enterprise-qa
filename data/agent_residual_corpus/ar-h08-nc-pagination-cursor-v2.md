---
doc_id: nc-pagination-cursor-v2
title: Northstar Pagination Cursor V2
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

# Northstar Pagination Cursor V2

## Current Rule

Walk a large result set page by page with the `cursor` parameter, following `next_cursor` until it is null.
