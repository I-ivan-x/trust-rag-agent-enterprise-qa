# Q5 Final Report

Generated from `data/claims/claim_registry.json`; do not edit numeric claims by hand.

Overall status: `scoped_negative_complete`.

## Formal conclusion

Q5 demonstrated a bounded selective runtime, observation completion, schema and transition safety, and hybrid efficiency within their named real-dev scopes. It did not demonstrate the preregistered LLM semantic uplift, and deterministic controls closed the frozen controlled-prose track. Open-world LLM value remains not evaluated.

## Sequential Boundary F evidence

The original Boundary F evidence remains 30/32 coverage. The later addendum is a separate evidence layer; it does not overwrite the historical artifact.

Addendum metrics within the frozen K0U parser-uncovered 32-case scope:

- previously_uncovered_cases_resolved: 32/32
- remaining_uncovered_cases: 0/32
- coverage: 1.0
- conditional_risk: 0.0
- abstention_count: 0

`controlled_prose_track=closed`; `K1=false`; Boundary G and new K1 data are not authorized.

## Real-run and request boundary

The historical protocol-v3 primary real-dev run made 210 model calls. Its Hybrid/LLM-only call ratio was 78/132 and token ratio was 66531/103246. The Boundary F addendum made 0 model requests and 0 external requests.

The semantic uplift was 1/12, below the frozen 0.10 value threshold. This is a current-scope negative result, not a claim that LLMs are generally without value.

No `q5_test` split was created or read during closure. The latest stable product release remains `v3.0-q4-reliability`; Q5 does not create a release or tag.

## Evidence boundary

Every number above is generated from registry claim IDs and hash-bound source artifacts. See `docs/Q5_CLAIM_MATRIX.md` for the per-claim evidence mapping.
