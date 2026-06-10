# Week 1 Demo Eval Case Review

This file is a Week 1 review aid for Owner/Claude. It is not a formal evaluation
report and must not be used as headline metrics. Gold chunks are backfilled only
from real generated fixture chunks.

For each case, the user context shows who is asking (used by the future ACL
gate), and each gold chunk lists the gate-relevant metadata (status,
access_level, conflict_group_id, is_authoritative) so the Owner can confirm the
expected behavior without cross-checking `chunks.jsonl` by hand.

## demo-001

- query: What is the refresh token rate limit in Auth Service API v2?
- query_type: single_doc_fact
- expected_behavior: answer
- user_role / department / clearance: employee / Engineering / internal
- gold_doc_ids: ['doc-api-auth-service-v2']
- gold_chunk_ids: ['doc-api-auth-service-v2::chunk-0002']

### doc-api-auth-service-v2::chunk-0002

- section_path: ['Auth Service API v2', 'Refresh Token Rate Limit']
- line_start / line_end: 45 / 46
- status: active
- access_level: internal
- conflict_group_id: auth-token-lifetime (document-level; not the contested field)
- is_authoritative: true
- text_preview: The refresh token endpoint is limited to 30 requests per minute per client. Requests above this limit receive an HTTP 429 response.

Confirm: chunk answers the rate-limit question (30 req/min) and is distinct from
the access-token-lifetime chunk. Needs Owner/Claude confirmation.

## demo-002

- query: What is the invoice export retention policy?
- query_type: no_evidence
- expected_behavior: refuse_no_evidence
- user_role / department / clearance: employee / Finance / internal
- gold_doc_ids: []
- gold_chunk_ids: []

Confirm: no document in the fixture corpus covers invoice export retention, so
gold_chunk_ids stays empty. Needs Owner/Claude confirmation.

## demo-003

- query: How often are admin keys rotated?
- query_type: permission_denied
- expected_behavior: refuse_permission
- user_role / department / clearance: employee / Engineering / internal
- gold_doc_ids: ['doc-security-admin-key-rotation-sop']
- gold_chunk_ids: ['doc-security-admin-key-rotation-sop::chunk-0000']

### doc-security-admin-key-rotation-sop::chunk-0000

- section_path: ['Admin Key Rotation SOP', 'Restricted Procedure']
- line_start / line_end: 36 / 36
- status: active
- access_level: restricted
- allowed_roles: ['security_admin']
- conflict_group_id: null
- is_authoritative: true
- text_preview: Admin keys must be rotated every 90 days by a security administrator.

Confirm: the chunk does answer the question, but access_level=restricted with
allowed_roles=[security_admin] excludes the employee asker, so the expected
behavior is refuse_permission rather than answer. Needs Owner/Claude
confirmation.

## demo-004

- query: What access token lifetime did Auth Service API v1 use?
- query_type: deprecated_doc
- expected_behavior: warn_deprecated
- user_role / department / clearance: employee / Engineering / internal
- gold_doc_ids: ['doc-api-auth-service-v1']
- gold_chunk_ids: ['doc-api-auth-service-v1::chunk-0000']

### doc-api-auth-service-v1::chunk-0000

- section_path: ['Auth Service API v1', 'Access Token Lifetime']
- line_start / line_end: 37 / 37
- status: deprecated
- access_level: internal
- conflict_group_id: auth-token-lifetime
- is_authoritative: false
- text_preview: In v1 the access token lifetime was 60 minutes.

Confirm: the only supporting chunk lives in a deprecated document, so the
expected behavior is warn_deprecated. Needs Owner/Claude confirmation.

## demo-005

- query: Is the access token lifetime 30 minutes or 60 minutes?
- query_type: conflict_doc
- expected_behavior: report_conflict
- user_role / department / clearance: employee / Engineering / internal
- gold_doc_ids: ['doc-api-auth-service-v2', 'doc-meeting-auth-token-lifetime-decision']
- gold_chunk_ids: ['doc-api-auth-service-v2::chunk-0000', 'doc-meeting-auth-token-lifetime-decision::chunk-0000']

### doc-api-auth-service-v2::chunk-0000

- section_path: ['Auth Service API v2', 'Access Token Lifetime']
- line_start / line_end: 37 / 37
- status: active
- access_level: internal
- conflict_group_id: auth-token-lifetime
- is_authoritative: true
- text_preview: In v2 the access token lifetime is 30 minutes.

### doc-meeting-auth-token-lifetime-decision::chunk-0000

- section_path: ['Auth Token Lifetime Decision Notes', 'Decision']
- line_start / line_end: 38 / 39
- status: active
- access_level: internal
- conflict_group_id: auth-token-lifetime
- is_authoritative: false
- text_preview: The team agreed to keep the access token lifetime at 60 minutes to reduce re-login friction during the v2 migration.

Minimal-conflict rule check (active-active + same conflict_group_id):

- both gold chunks have status = active;
- both share conflict_group_id = auth-token-lifetime;
- they disagree on the value (30 vs 60 minutes);
- the deprecated v1 chunk (doc-api-auth-service-v1::chunk-0000, same group) is
  intentionally excluded, since active-vs-deprecated routes to warn_deprecated,
  not report_conflict.

Confirm: the two active sources genuinely conflict and the system should report
both citations rather than choose one. Needs Owner/Claude confirmation.
