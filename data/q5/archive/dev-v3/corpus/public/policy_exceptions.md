# Q5 Dev Policy Exception Semantics

## q5-dev-d05-doc

The billing exporter configuration violates policy:change-control and requires a remediation record.

## q5-dev-d06-doc

The audit archive setting violates policy:retention and has no runtime ambiguity.

## q5-dev-s01-doc

resource:checkout-exporter violates policy:change-control. The current exception state must be observed. A matching active waiver pauses remediation for human review; a waiver for another deployment scope leaves the violation actionable.

## q5-dev-s02-doc

resource:settlement-worker violates policy:change-control. The current exception state must be observed. A matching active waiver pauses remediation for human review; a waiver for another deployment scope leaves the violation actionable.

## q5-dev-s03-doc

resource:invoice-renderer violates policy:deployment-window. The current exception state must be observed. A matching active tracking exception requires a remediation ticket under the exception record; a scope mismatch requires human ownership review.

## q5-dev-s04-doc

resource:tax-calculator violates policy:change-control. The current exception state must be observed. A matching active tracking exception requires a remediation ticket under the exception record; a scope mismatch requires human ownership review.
