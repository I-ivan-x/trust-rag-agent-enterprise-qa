# P3-09 Diagnostic Precheck

- run_id: `p3-09-diagnostic-precheck`
- created_at: `2026-06-18T07:36:57.949336+00:00`
- mode: zero-token diagnostic precheck
- llm_call_count: 0
- llm_usage_total_tokens: 0
- case_count: 25
- weak_recall/action-a trigger_count: 3
- weak_recall bed sufficient (>=8): False

## Diagnostic Distribution

| failure_type | count |
| --- | ---: |
| `NO_RECOVERY` | 20 |
| `PERMISSION_BLOCKED` | 2 |
| `WEAK_RECALL` | 3 |

## Legal Action Distribution

| legal_actions | count |
| --- | ---: |
| `none` | 20 |
| `refuse_with_explanation` | 2 |
| `rewrite_query,refuse_with_explanation` | 3 |

## By Split

| split | cases | weak_recall triggers | failure_distribution |
| --- | ---: | ---: | --- |
| `agent_residual` | 10 | 2 | `{"NO_RECOVERY": 8, "WEAK_RECALL": 2}` |
| `obfuscated` | 15 | 1 | `{"NO_RECOVERY": 12, "PERMISSION_BLOCKED": 2, "WEAK_RECALL": 1}` |

## Notes

- RECORD not HALT: the precheck archives real diagnostic scarcity instead of requiring >=6 a/b co-occurrence.
- Action d is retained for attribution, but overlaps Q1 `report_conflict`; it is not a primary P3-09 ability readout.

## Per Case

| split | case_id | failure_type | legal_actions | clean | depr | restr | entity_miss | top_score | gold_doc@5 |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| `obfuscated` | `obfuscated-001` | `NO_RECOVERY` | `none` | 4 | 1 | 1 | False | 0.9710 | False |
| `obfuscated` | `obfuscated-002` | `NO_RECOVERY` | `none` | 5 | 1 | 0 | False | 0.9260 | True |
| `obfuscated` | `obfuscated-003` | `NO_RECOVERY` | `none` | 5 | 0 | 3 | False | 0.5557 | True |
| `obfuscated` | `obfuscated-004` | `NO_RECOVERY` | `none` | 7 | 0 | 1 | False | 0.6596 | False |
| `obfuscated` | `obfuscated-005` | `NO_RECOVERY` | `none` | 2 | 6 | 0 | False | 0.0156 | True |
| `obfuscated` | `obfuscated-006` | `NO_RECOVERY` | `none` | 8 | 0 | 0 | False | 0.1960 | True |
| `obfuscated` | `obfuscated-007` | `NO_RECOVERY` | `none` | 7 | 0 | 1 | False | 0.9564 | True |
| `obfuscated` | `obfuscated-008` | `NO_RECOVERY` | `none` | 8 | 0 | 0 | False | 0.4170 | True |
| `obfuscated` | `obfuscated-009` | `NO_RECOVERY` | `none` | 7 | 0 | 1 | False | 0.8812 | True |
| `obfuscated` | `obfuscated-010` | `NO_RECOVERY` | `none` | 4 | 2 | 2 | False | 0.2770 | True |
| `obfuscated` | `obfuscated-011` | `NO_RECOVERY` | `none` | 4 | 3 | 0 | False | 0.5049 | True |
| `obfuscated` | `obfuscated-012` | `PERMISSION_BLOCKED` | `refuse_with_explanation` | 0 | 4 | 0 | True | 0.0594 | True |
| `obfuscated` | `obfuscated-013` | `PERMISSION_BLOCKED` | `refuse_with_explanation` | 0 | 4 | 0 | True | 0.0681 | True |
| `obfuscated` | `obfuscated-014` | `NO_RECOVERY` | `none` | 1 | 4 | 2 | False | 0.0311 | True |
| `obfuscated` | `obfuscated-015` | `WEAK_RECALL` | `rewrite_query,refuse_with_explanation` | 0 | 8 | 0 | True | 0.1066 | True |
| `agent_residual` | `AR-001` | `WEAK_RECALL` | `rewrite_query,refuse_with_explanation` | 5 | 3 | 0 | True | 0.6249 | True |
| `agent_residual` | `AR-002` | `WEAK_RECALL` | `rewrite_query,refuse_with_explanation` | 4 | 4 | 0 | True | 0.7956 | True |
| `agent_residual` | `AR-003` | `NO_RECOVERY` | `none` | 5 | 3 | 0 | False | 0.0593 | True |
| `agent_residual` | `AR-004` | `NO_RECOVERY` | `none` | 5 | 3 | 0 | False | 0.8091 | True |
| `agent_residual` | `AR-005` | `NO_RECOVERY` | `none` | 4 | 4 | 0 | False | 0.3268 | True |
| `agent_residual` | `AR-006` | `NO_RECOVERY` | `none` | 6 | 2 | 0 | False | 0.0108 | True |
| `agent_residual` | `AR-007` | `NO_RECOVERY` | `none` | 5 | 3 | 0 | False | 0.9373 | True |
| `agent_residual` | `AR-008` | `NO_RECOVERY` | `none` | 4 | 4 | 0 | False | 0.7750 | True |
| `agent_residual` | `AR-009` | `NO_RECOVERY` | `none` | 6 | 2 | 0 | False | 0.0129 | True |
| `agent_residual` | `AR-010` | `NO_RECOVERY` | `none` | 8 | 0 | 0 | False | 0.9911 | True |
