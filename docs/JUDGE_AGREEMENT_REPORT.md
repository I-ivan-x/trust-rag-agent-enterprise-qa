# Judge Agreement Report

Run: `data/eval_runs/judge-agreement-v1`, generated 2026-06-15 with
`JUDGE_LLM_PROVIDER=xiaomi`, `JUDGE_LLM_MODEL_NAME=mimo-v2.5-pro`,
`temperature=0`.

## Scope

- `judge_based=true`; this is not headline evaluation and must not be reported
  as human citation accuracy.
- Real anchor set: n=15, with 11 `supported` and 4 `weak` labels.
- The anchor set has 0 real `unsupported` and 0 real `wrong_side` labels, so
  unsupported/wrong-side detection is probe-only until rewritten hard-negative
  anchors land.

## Result

No candidate is deployable for downstream judge-based metrics.

| candidate | binary_agreement | exact_agreement | kappa_binary | probe_floor | deployable |
| --- | ---: | ---: | ---: | ---: | --- |
| `ragas` | 0.7333 | 0.7333 | 0.0000 | 3/5 | no |
| `deepeval` | 0.7333 | 0.7333 | 0.0000 | 3/5 | no |
| `custom` | 0.7333 | 0.7333 | 0.0000 | 3/5 | no |

All three candidates predicted every real anchor as `supported`, missing the
four human `weak` labels. On probes, all three caught the three unsupported
cases but missed both `wrong_side` cases. Therefore each candidate fails both
the G2 hard gate (`binary_agreement >= 0.80`) and the probe hard gate
(`probe_floor >= 4/5`).

Framework candidates are implemented as prompt adapters over the same
secondary-family judge model; this P2 implementation does not add RAGAS or
DeepEval as hard runtime dependencies.

## Selection

- deploy_judge: `false`
- selected_candidate: `null`
- reason: no candidate passed both G2 and PROBE.

## Conclusion (interpretation)

The harness did its job: it **refused to deploy a judge that cannot
discriminate.** This is the intended governance-as-code outcome, not a setback.

In order of importance:

1. **The decisive finding is wrong-side blindness.** Every candidate caught the
   3 planted `unsupported` probes but missed both `wrong_side` probes (0/2).
   Wrong-side citation — citing a right-looking but wrong document (failure
   class F4) — is the single most important thing an automated citation judge
   would need to catch, and this judge cannot. That alone disqualifies
   deployment, independent of the agreement gate.

2. **The finding is narrow and must be reported as such.** All three
   "candidates" returned identical numbers because they are three prompt
   strategies over the *same* secondary-family model (MiMo), not the actual
   RAGAS/DeepEval libraries. The result therefore measures *this judge model's*
   discrimination on this task — it is **not** evidence that "RAGAS is bad" or
   that LLM-judges fail in general, and no framework benchmark may be claimed.

3. **The judge collapsed to "always supported"** (`kappa=0` confirms zero
   agreement beyond chance). On this easy anchor set the 11 `supported` cases
   are near-verbatim and the 4 `weak` cases are degenerate claim *strings* that
   are nonetheless present in the cited text; a surface-matching judge calls all
   15 supported. Detecting `weak` requires judging the claim's own quality,
   which the judge did not do.

### Implications

- No judge deployed. Claim-support stays **human-only** — the 15-case human
  census (`CITATION_AUDIT.md`) remains the citation-support evidence.
- Phase 2 judge-dependent items are **descoped per spec**: no judge-based
  `unsupported_claim_rate` backfill (P2-05); the Phase 3 runtime verifier
  (package decision B) cannot rely on an automated judge and must fall back to
  human/rule-based or be dropped.
- A future revisit (stronger judge model, the real libraries, or a richer anchor
  set with real `unsupported`/`wrong_side` once C2-05 lands) could reopen this.
  The `deploy_judge=false` decision is correct on current evidence.

### Honest narrative

"I built an agreement harness with a discrimination floor, and it rejected my
own automated citation judge: the candidate could verify near-verbatim support
but could not detect wrong-side citations, so I did not deploy it and kept
citation-support human-verified." This is evaluation maturity — a gate that
fails closed on its own tooling.

## Artifacts

- `data/eval_runs/judge-agreement-v1/agreement_summary.json`
- `data/eval_runs/judge-agreement-v1/ragas_verdicts.jsonl`
- `data/eval_runs/judge-agreement-v1/deepeval_verdicts.jsonl`
- `data/eval_runs/judge-agreement-v1/custom_verdicts.jsonl`
- `data/eval_runs/judge-agreement-v1/probe_verdicts.jsonl`
