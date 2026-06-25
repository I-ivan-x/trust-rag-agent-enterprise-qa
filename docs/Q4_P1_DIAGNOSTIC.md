# Q4-P1 Diagnostic (auto-generated companion)

- run_id: `q4-p1-diagnostic`
- created_at: `2026-06-25T08:43:20.739738+00:00`
- mode: zero_token_governance_diagnostic (controller=rule, llm_calls=0, sink_writes=0)
- vector_unavailable: False
- stale_gold: 3 | detection_miss: 3 | routing_error: 0
- over_escalation_count: 4
- dead_path_decision: `fix_detection_3_3`

| case | gold_cond | gold_action | detected | ev | auth_actor | proposed | stale? | dead_path | over_esc | trigger |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ora-001` | STALE_PROCEDURE | flag_stale | `-` | sufficient | True | no_op | False | detection_miss | False | - |
| `ora-002` | STALE_PROCEDURE | flag_stale | `PERMISSION_BLOCKED` | sufficient | True | escalate_to_human | False | detection_miss | True | permission_blocked |
| `ora-003` | STALE_PROCEDURE | flag_stale | `PERMISSION_BLOCKED` | sufficient | True | escalate_to_human | False | detection_miss | True | permission_blocked |
| `ora-004` | CONFIG_VIOLATION | open_remediation_ticket | `CONFIG_VIOLATION` | sufficient | True | open_remediation_ticket | False | - | False | - |
| `ora-005` | BROKEN_XREF | open_remediation_ticket | `PERMISSION_BLOCKED` | sufficient | True | escalate_to_human | False | - | True | permission_blocked |
| `ora-006` | CONFIG_VIOLATION | open_remediation_ticket | `CONFIG_VIOLATION` | sufficient | True | open_remediation_ticket | False | - | False | - |
| `ora-007` | ACTIVE_ACTIVE_CONFLICT | send_alert | `ACTIVE_ACTIVE_CONFLICT` | sufficient | True | send_alert | False | - | False | - |
| `ora-008` | ACTIVE_ACTIVE_CONFLICT | send_alert | `ACTIVE_ACTIVE_CONFLICT,BROKEN_XREF,MISSING_PREREQ` | sufficient | True | send_alert | False | - | False | - |
| `ora-009` | PERMISSION_BLOCKED | escalate_to_human | `PERMISSION_BLOCKED,CONFIG_VIOLATION` | sufficient | False | escalate_to_human | False | - | False | permission_blocked |
| `ora-010` | PERMISSION_BLOCKED | escalate_to_human | `PERMISSION_BLOCKED` | sufficient | False | escalate_to_human | False | - | False | permission_blocked |
| `ora-011` | PERMISSION_BLOCKED | escalate_to_human | `PERMISSION_BLOCKED,CONFIG_VIOLATION` | sufficient | False | escalate_to_human | False | - | False | permission_blocked |
| `ora-012` | INSUFFICIENT_EVIDENCE | escalate_to_human | `-` | sufficient | True | no_op | False | - | False | - |
| `ora-013` | none | no_op | `-` | sufficient | True | no_op | False | - | False | - |
| `ora-014` | none | no_op | `PERMISSION_BLOCKED` | insufficient | True | escalate_to_human | False | - | True | permission_blocked |
