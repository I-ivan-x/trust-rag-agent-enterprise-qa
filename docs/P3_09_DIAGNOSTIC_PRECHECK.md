# P3-09 Diagnostic Precheck

- run_id: `p3-09-diagnostic-precheck`
- created_at: `2026-06-24T07:22:30.479511+00:00`
- mode: zero-token diagnostic precheck
- llm_call_count: 0
- llm_usage_total_tokens: 0
- case_count: 33
- weak_recall/action-a trigger_count: 2
- action-b policy-neighbor surface_count: 25
- action-b legal trigger_count: 0
- action-b filter-recoverable count: 3
- action-b gold-doc-recoverable count: 0
- action-d active-conflict surface_count: 1
- action-d legal trigger_count: 0
- weak_recall bed sufficient (>=8): False

## Diagnostic Distribution

| failure_type | count |
| --- | ---: |
| `NO_RECOVERY` | 29 |
| `PERMISSION_BLOCKED` | 2 |
| `WEAK_RECALL` | 2 |

## Legal Action Distribution

| legal_actions | count |
| --- | ---: |
| `none` | 29 |
| `refuse_with_explanation` | 2 |
| `rewrite_query,refuse_with_explanation` | 2 |

## By Split

| split | cases | a triggers | b policy | b legal | b recoverable | d surface | d legal | failure_distribution |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `agent_residual` | 18 | 1 | 16 | 0 | 0 | 1 | 0 | `{"NO_RECOVERY": 17, "WEAK_RECALL": 1}` |
| `obfuscated` | 15 | 1 | 9 | 0 | 3 | 0 | 0 | `{"NO_RECOVERY": 12, "PERMISSION_BLOCKED": 2, "WEAK_RECALL": 1}` |

## Notes

- RECORD not HALT: the precheck archives real diagnostic scarcity instead of requiring >=6 a/b co-occurrence.
- Action d is retained for attribution, but overlaps Q1 `report_conflict`; it is not a primary P3-09 ability readout.

## Per Case

| split | case_id | failure_type | legal_actions | clean | policy | entity_miss | a | b_legal | b_save | d_surface | d_legal | gold_doc@5 |
| --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| `obfuscated` | `obfuscated-001` | `NO_RECOVERY` | `none` | 4 | 2 | False | False | False | False | False | False | False |
| `obfuscated` | `obfuscated-002` | `NO_RECOVERY` | `none` | 5 | 1 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-003` | `NO_RECOVERY` | `none` | 5 | 3 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-004` | `NO_RECOVERY` | `none` | 7 | 1 | False | False | False | False | False | False | False |
| `obfuscated` | `obfuscated-005` | `NO_RECOVERY` | `none` | 2 | 6 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-006` | `NO_RECOVERY` | `none` | 8 | 0 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-007` | `NO_RECOVERY` | `none` | 7 | 1 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-008` | `NO_RECOVERY` | `none` | 8 | 0 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-009` | `NO_RECOVERY` | `none` | 7 | 1 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-010` | `NO_RECOVERY` | `none` | 4 | 4 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-011` | `NO_RECOVERY` | `none` | 4 | 3 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-012` | `PERMISSION_BLOCKED` | `refuse_with_explanation` | 0 | 4 | True | False | False | True | False | False | True |
| `obfuscated` | `obfuscated-013` | `PERMISSION_BLOCKED` | `refuse_with_explanation` | 0 | 4 | True | False | False | True | False | False | True |
| `obfuscated` | `obfuscated-014` | `NO_RECOVERY` | `none` | 1 | 6 | False | False | False | False | False | False | True |
| `obfuscated` | `obfuscated-015` | `WEAK_RECALL` | `rewrite_query,refuse_with_explanation` | 0 | 8 | True | True | False | True | False | False | True |
| `agent_residual` | `AR-001` | `NO_RECOVERY` | `none` | 6 | 2 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-002` | `WEAK_RECALL` | `rewrite_query,refuse_with_explanation` | 4 | 4 | True | True | False | False | False | False | True |
| `agent_residual` | `AR-003` | `NO_RECOVERY` | `none` | 6 | 2 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-004` | `NO_RECOVERY` | `none` | 5 | 3 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-005` | `NO_RECOVERY` | `none` | 5 | 3 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-006` | `NO_RECOVERY` | `none` | 6 | 2 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-007` | `NO_RECOVERY` | `none` | 6 | 2 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-008` | `NO_RECOVERY` | `none` | 5 | 3 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-009` | `NO_RECOVERY` | `none` | 6 | 2 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-010` | `NO_RECOVERY` | `none` | 8 | 0 | False | False | False | False | True | False | True |
| `agent_residual` | `AR-H01` | `NO_RECOVERY` | `none` | 5 | 3 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-H02` | `NO_RECOVERY` | `none` | 3 | 5 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-H03` | `NO_RECOVERY` | `none` | 5 | 3 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-H04` | `NO_RECOVERY` | `none` | 6 | 2 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-H05` | `NO_RECOVERY` | `none` | 6 | 2 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-H06` | `NO_RECOVERY` | `none` | 6 | 2 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-H07` | `NO_RECOVERY` | `none` | 7 | 1 | False | False | False | False | False | False | True |
| `agent_residual` | `AR-H08` | `NO_RECOVERY` | `none` | 5 | 3 | False | False | False | False | False | False | True |
