# Week 1 Demo Eval Case Review

This file is a Week 1 review aid for Owner/Claude. It is not a formal evaluation report and must not be used as headline metrics.

## demo-001

- query: What is the refresh token rate limit in Auth Service API v2?
- expected_behavior: answer
- gold_doc_ids: ['doc-api-auth-service-v2']
- gold_chunk_ids: ['doc-api-auth-service-v2::chunk-0002']

### doc-api-auth-service-v2::chunk-0002

- doc_id: doc-api-auth-service-v2
- section_path: ['Auth Service API v2', 'Refresh Token Rate Limit']
- text_preview: The refresh token endpoint is limited to 30 requests per minute per client. Requests above this limit receive an HTTP 429 response.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## demo-002

- query: What is the invoice export retention policy?
- expected_behavior: refuse_no_evidence
- gold_doc_ids: []
- gold_chunk_ids: []

Needs Owner/Claude confirmation: no supporting chunk is expected.

## demo-003

- query: How often are admin keys rotated?
- expected_behavior: refuse_permission
- gold_doc_ids: ['doc-security-admin-key-rotation-sop']
- gold_chunk_ids: ['doc-security-admin-key-rotation-sop::chunk-0000']

### doc-security-admin-key-rotation-sop::chunk-0000

- doc_id: doc-security-admin-key-rotation-sop
- section_path: ['Admin Key Rotation SOP', 'Restricted Procedure']
- text_preview: Admin keys must be rotated every 90 days by a security administrator.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## demo-004

- query: What access token lifetime did Auth Service API v1 use?
- expected_behavior: warn_deprecated
- gold_doc_ids: ['doc-api-auth-service-v1']
- gold_chunk_ids: ['doc-api-auth-service-v1::chunk-0000']

### doc-api-auth-service-v1::chunk-0000

- doc_id: doc-api-auth-service-v1
- section_path: ['Auth Service API v1', 'Access Token Lifetime']
- text_preview: In v1 the access token lifetime was 60 minutes.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## demo-005

- query: Is the access token lifetime 30 minutes or 60 minutes?
- expected_behavior: report_conflict
- gold_doc_ids: ['doc-api-auth-service-v2', 'doc-meeting-auth-token-lifetime-decision']
- gold_chunk_ids: ['doc-api-auth-service-v2::chunk-0000', 'doc-meeting-auth-token-lifetime-decision::chunk-0000']

### doc-api-auth-service-v2::chunk-0000

- doc_id: doc-api-auth-service-v2
- section_path: ['Auth Service API v2', 'Access Token Lifetime']
- text_preview: In v2 the access token lifetime is 30 minutes.

### doc-meeting-auth-token-lifetime-decision::chunk-0000

- doc_id: doc-meeting-auth-token-lifetime-decision
- section_path: ['Auth Token Lifetime Decision Notes', 'Decision']
- text_preview: The team agreed to keep the access token lifetime at 60 minutes to reduce re-login friction during the v2 migration.

Needs Owner/Claude confirmation: verify gold chunk relevance.
