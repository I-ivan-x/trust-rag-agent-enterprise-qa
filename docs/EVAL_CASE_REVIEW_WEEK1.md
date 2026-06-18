# Week 1 Demo Eval Case Review

This file is a Week 1 review aid for Owner/Claude. It is not a formal evaluation report and must not be used as headline metrics.

## AR-001

- query: Need auth token ttl before renewal?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-001-gold']
- gold_chunk_ids: ['doc-ar-001-gold::chunk-0000']

### doc-ar-001-gold::chunk-0000

- doc_id: doc-ar-001-gold
- section_path: ['Residual AR001 Access Token Lifetime', 'Current Rule']
- text_preview: For the auth service, the access token lifetime is 30 minutes before renewal.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-002

- query: Refresh rlimit after auth client?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-002-gold']
- gold_chunk_ids: ['doc-ar-002-gold::chunk-0000']

### doc-ar-002-gold::chunk-0000

- doc_id: doc-ar-002-gold
- section_path: ['Residual AR002 Refresh Token Rate Limit', 'Current Rule']
- text_preview: The refresh token rate limit is 45 refresh requests per minute for each client.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-003

- query: WH retry wait after failed delivery?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-003-gold']
- gold_chunk_ids: ['doc-ar-003-gold::chunk-0000']

### doc-ar-003-gold::chunk-0000

- doc_id: doc-ar-003-gold
- section_path: ['Residual AR003 Webhook Retry Window', 'Current Rule']
- text_preview: Webhook delivery retries remain eligible for 12 hours after the first failed attempt.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-004

- query: Sess idle cutoff for console users?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-004-gold']
- gold_chunk_ids: ['doc-ar-004-gold::chunk-0000']

### doc-ar-004-gold::chunk-0000

- doc_id: doc-ar-004-gold
- section_path: ['Residual AR004 Session Idle Timeout', 'Current Rule']
- text_preview: The console session idle timeout is 18 minutes for standard employee accounts.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-005

- query: Invoice xport retention cleanup timing?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-005-gold']
- gold_chunk_ids: ['doc-ar-005-gold::chunk-0000']

### doc-ar-005-gold::chunk-0000

- doc_id: doc-ar-005-gold
- section_path: ['Residual AR005 Invoice Export Retention', 'Current Rule']
- text_preview: Invoice export files are retained for 14 days before automatic cleanup.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-006

- query: Fflag rollout lag for workers?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-006-gold']
- gold_chunk_ids: ['doc-ar-006-gold::chunk-0000']

### doc-ar-006-gold::chunk-0000

- doc_id: doc-ar-006-gold
- section_path: ['Residual AR006 Feature Flag Propagation Delay', 'Current Rule']
- text_preview: Feature flag changes propagate to production workers within 6 minutes.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-007

- query: Audit cursor grace after rotation?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-007-gold']
- gold_chunk_ids: ['doc-ar-007-gold::chunk-0000']

### doc-ar-007-gold::chunk-0000

- doc_id: doc-ar-007-gold
- section_path: ['Residual AR007 Audit Cursor Grace Period', 'Current Rule']
- text_preview: Audit cursor tokens have a grace period of 9 minutes after rotation.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-008

- query: Cache warmup dr before pause?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-008-gold']
- gold_chunk_ids: ['doc-ar-008-gold::chunk-0000']

### doc-ar-008-gold::chunk-0000

- doc_id: doc-ar-008-gold
- section_path: ['Residual AR008 Cache Warmup Drift', 'Current Rule']
- text_preview: Cache warmup drift is tolerated for 4 minutes before the rollout is paused.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-009

- query: How long is the migration lockout?
- expected_behavior: answer
- gold_doc_ids: ['doc-ar-009-gold']
- gold_chunk_ids: ['doc-ar-009-gold::chunk-0000']

### doc-ar-009-gold::chunk-0000

- doc_id: doc-ar-009-gold
- section_path: ['Residual AR009 Search Index Freeze Window', 'Current Rule']
- text_preview: Search index freeze windows last 25 minutes during the nightly migration.

Needs Owner/Claude confirmation: verify gold chunk relevance.

## AR-010

- query: Payroll batch window start for regions?
- expected_behavior: report_conflict
- gold_doc_ids: ['doc-ar-010-conflict-a', 'doc-ar-010-conflict-b']
- gold_chunk_ids: ['doc-ar-010-conflict-a::chunk-0000', 'doc-ar-010-conflict-b::chunk-0000']

### doc-ar-010-conflict-a::chunk-0000

- doc_id: doc-ar-010-conflict-a
- section_path: ['Residual AR010 Payroll Batch Window East', 'Current Statement']
- text_preview: Payroll batch jobs for the east region start at 01:15 UTC during the maintenance window.

### doc-ar-010-conflict-b::chunk-0000

- doc_id: doc-ar-010-conflict-b
- section_path: ['Residual AR010 Payroll Batch Window West', 'Current Statement']
- text_preview: Payroll batch jobs for the west region start at 02:45 UTC during the maintenance window.

Needs Owner/Claude confirmation: verify gold chunk relevance.
