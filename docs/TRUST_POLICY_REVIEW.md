# Trust Policy Review

Week 4 review template for the trust gates and refusal controller. This is a
design review aid, not a formal evaluation report.

## Review Checklist

- Response mode priority matches
  `refuse_permission > report_conflict > warn_deprecated > answer/refuse_no_evidence`.
- ACL-blocked chunk text does not appear in final answers or answer context.
- Deprecated evidence produces warning behavior instead of current-answer
  behavior when the query targets deprecated material.
- Active-active conflict produces `report_conflict` with citations.
- No-evidence cases refuse after at most one rewrite.
- Rewrite trace records original query, rewritten query, pass count, and
  evidence sufficiency.
- Fixture and mock outputs remain excluded from formal metrics.

## Reviewer Notes

Claude can review policy wording and failure modes. Codex owns code, tests, and
the final implementation in this repository.
