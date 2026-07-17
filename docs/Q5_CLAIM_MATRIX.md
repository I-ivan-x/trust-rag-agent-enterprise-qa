# Q5 Claim Matrix

Generated from `data/claims/claim_registry.json`; do not edit by hand.

Overall Q5 status: `scoped_negative_complete`.

| Claim | Public conclusion | Scope | Evidence | Headline |
| --- | --- | --- | --- | --- |
| `q5.selective_runtime_architecture` — Selective runtime architecture | Demonstrated within the frozen scope | Protocol-v3 primary real-dev run across 36 cases and three systems | `data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/summary.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`)<br>`data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/manifest.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`)<br>`data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/graded_manifest.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`)<br>`data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/gates.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`) | no |
| `q5.observation_adaptation` — Observation adaptation | Demonstrated within the frozen scope | Protocol-v3 hybrid system in the primary real-dev run | `data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/summary.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`) | no |
| `q5.schema_transition_safety` — Schema and transition safety | Demonstrated within the frozen scope | Protocol-v3 hybrid system over 108 real-dev trials | `data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/summary.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`) | no |
| `q5.hybrid_efficiency` — Hybrid efficiency | Demonstrated within the frozen scope | Hybrid versus LLM-only in the protocol-v3 primary real-dev run | `data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/summary.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`) | no |
| `q5.llm_semantic_uplift` — LLM semantic uplift | Falsified in the current scope | Protocol-v3 semantic stratum in the primary real-dev run | `data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/summary.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`)<br>`data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/gates.json` (`q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3`) | yes |
| `q5.controlled_prose_llm_necessity` — Controlled-prose LLM necessity | Falsified in the current scope | Frozen K0U parser-uncovered 32-case controlled-prose scope | `data/q5_frontier/dev-k0u-audit/boundary_f_summary.json` (`q5-boundary-f-k0u`)<br>`data/eval_runs/q5-boundary-f-addendum-z-a/addendum_metrics.json` (`q5-boundary-f-addendum-z-a`) | yes |
| `q5.open_world_llm_value` — Open-world LLM value | Not evaluated | Open-world policy language outside the frozen controlled-prose benchmark | `data/eval_runs/q5-boundary-f-addendum-z-a/addendum_metrics.json` (`q5-boundary-f-addendum-z-a`) | no |

The controlled-prose track is closed. K1, Boundary G, and new K1 data are not authorized. Open-world LLM value is not evaluated.
