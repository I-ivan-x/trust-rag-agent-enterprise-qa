# Q5 Dev Change Lifecycle Semantics

## q5-dev-d03-doc

The checkout rollback procedure was replaced by the current recovery guide and must be marked stale.

## q5-dev-d04-doc

The search index rebuild instructions are retired and the replacement procedure is already authoritative.

## q5-dev-d10-doc

The certificate rotation procedure lacks its required trust-store prerequisite and needs remediation.

## q5-dev-s05-doc

resource:checkout-failover-runbook is governed by change:checkout-failover-v2. Under the cutover policy, a completed replacement makes the runbook stale; a merely planned replacement requires human review.

## q5-dev-s06-doc

resource:search-recovery-runbook is governed by change:search-recovery-v3. Under the cutover policy, a completed replacement makes the runbook stale; a merely planned replacement requires human review.

## q5-dev-s07-doc

resource:data-export-runbook is governed by change:data-export-v4. Under the archival-hold policy, a planned replacement immediately marks the runbook stale; a completed replacement requires human archival review.

## q5-dev-s08-doc

resource:cache-warmup-runbook is governed by change:cache-warmup-v3. Under the archival-hold policy, a planned replacement immediately marks the runbook stale; a completed replacement requires human archival review.
