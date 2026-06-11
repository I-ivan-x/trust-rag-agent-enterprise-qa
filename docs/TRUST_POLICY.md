# Trust Policy

This Week 4 policy describes runtime behavior for local demo and regression
checks. It is not a formal evaluation report.

## Response Modes

TrustRAG Enterprise QA uses exactly six Q1 response modes:

- `answer`
- `refuse_no_evidence`
- `refuse_permission`
- `warn_deprecated`
- `report_conflict`
- `system_error`

The decision priority is:

```text
refuse_permission > report_conflict > warn_deprecated > answer/refuse_no_evidence
```

`ask_clarification` is not a Q1 response mode.

## Document State Gate

- `active` chunks can survive.
- `deprecated` chunks are withheld from normal answer evidence and can produce
  `warn_deprecated` when the query targets deprecated or legacy material.
- `archived` and `draft` chunks are blocked.
- Active-vs-deprecated chunks in the same conflict group do not trigger minimal
  conflict detection.

## ACL Gate

- `public` chunks are visible to all users.
- `internal` chunks require at least internal clearance.
- `confidential` chunks require confidential clearance.
- `restricted` chunks require `user_role` to appear in `allowed_roles`.
- ACL-blocked chunk text must not enter answer context or permission-denied
  responses.

## Minimal Conflict Detection

Week 4 detects only P0 active-active conflicts after state and ACL gates. A
conflict is reported when at least two different active documents share the same
non-empty `conflict_group_id`. The system reports conflict and cites the sources
without deciding which source is correct.

## Evidence Gate

The simplified Week 4 evidence gate marks evidence insufficient when no
surviving chunks remain, support count is below the minimum, score is below an
explicit threshold, or rule-based entity matching misses the surviving evidence.

## Agentic Recovery

Rule-based query rewrite is limited to one second pass. The second pass still
runs retrieval, rerank, document state gate, ACL gate, conflict detection, and
evidence gate. Rewrite cannot expand permissions or bypass ACL.

## Mock Boundary

Mock embedding, mock reranker, and mock LLM providers are valid only for tests,
CI, local demo, and smoke checks. Fixture/demo results are not headline metrics
and must not be reported as formal evaluation.

## Known Limitations

- Evidence matching is rule-based and intentionally simple.
- Minimal conflict detection does not judge which source is authoritative.
- Citation verifier v1 and formal evaluation are Week 5+ work.
- JSONL trace logging is not implemented in Week 4.
