# LLM Judge Protocol — Anchored Selection & Custom Judge Design (v1 draft)

Status: draft for Q2 Phase 2 (ROADMAP P2-01..P2-06).
Hard prerequisite: the manual citation-support audit (pass 1 + re-label) is
complete — its labeled claims are the anchor set. No judge may be used for any
reported metric before passing the selection gate in §5.

Core principle: **an unvalidated LLM judge is an opinion, not a metric.**
This protocol exists to turn one judge into a metric, with evidence.

------

## 1. Task Definition

Judged unit (identical to the human audit unit): one (claim, cited chunk set)
pair. The judge answers: *do the cited chunks support this claim?*

Output space: `supported | weak | unsupported`, plus boolean
`wrong_side_citation` — same definitions as the human rules in
`CITATION_AUDIT_GUIDE.md` §5. The judge prompt deliberately mirrors those
rules verbatim: maximizing judge–human agreement starts with giving the judge
the same rulebook the human used.

## 2. Candidates

| id | Candidate | Granularity note |
| --- | --- | --- |
| J-A | RAGAS faithfulness | Statement-level verdicts extracted from its decomposition; mapped to binary supported/not |
| J-B | DeepEval FaithfulnessMetric / G-Eval rubric | Per-claim verdicts where the framework exposes them; otherwise binary mapping |
| J-C | Custom domain judge (§6 prompt) | Native 3-way + wrong_side, per-claim |

Framework candidates are evaluated as shipped (reasonable default config,
documented), not tuned — the comparison is "off-the-shelf vs domain-tailored",
and tuning J-A/J-B would blur it.

**Input harmonization (critical for a fair comparison).** All three candidates
judge the *identical* (claim_text, cited_chunks) pair. For RAGAS, each claim
is submitted as the "answer" with its cited chunks as "contexts" —
deliberately bypassing RAGAS's own answer decomposition. Letting frameworks
re-decompose full answers would produce statement units that do not align
with the human-labeled anchor units, making agreement uncomputable.

## 3. Judge Model Requirements

- **Different model family from the system under evaluation** (DeepSeek).
  Self-preference bias is a known failure mode; this is a hard rule.
- The **same judge model** powers all three candidates, so the comparison
  isolates method/prompt, not model.
- temperature=0, structured output, fixed version pinned in the run record.
- Judge sees only: claim text + frozen cited-text snapshots (from the anchor
  file). It must not see gold answers, human labels, system names, or full
  documents.

## 4. Agreement Measurement

Against human **pass-1** labels on the full anchor set (25–40 claims):

```text
binary_agreement   primary axis: supported vs (weak + unsupported);
                   the only axis on which all three candidates are comparable
exact_agreement    3-way, J-C only
cohen_kappa        binary, all candidates (guards against base-rate inflation)
per_stratum        external / hard_negative / obfuscated; n<5 strata reported
                   as counts, not percentages
wrong_side_recall  J-C only, on hard-negative anchors: of human-flagged
                   wrong_side citations, how many the judge catches
```

Report 95% bootstrap intervals and state plainly that with n≤40 they are wide.
That honesty does not block selection — the gate in §5 is designed for small n.

## 5. Selection Gate

A candidate is **usable for reported metrics** only if, on the anchor set:

```text
G1  binary_agreement ≥ human self-consistency (binary) − 0.05
G2  binary_agreement ≥ 0.80 absolute
G3  no stratum with n≥8 where agreement < 0.70
```

Rationale for G1: a judge cannot be expected to agree with the human more than
the human agrees with themselves one week later; the self-consistency number
from the audit is the ceiling, and G1 anchors the bar to it.

Gate weighting: **G2 is the hard gate.** G1's ceiling is estimated from only
8–10 re-labeled items and is itself noisy. Treat G1 as advisory; if a
selection decision hinges on G1 alone, expand the re-label set first rather
than ruling a candidate in or out on a noisy ceiling.

Outcomes:

- ≥1 candidate passes → select the highest binary_agreement; tie-break toward
  J-C if its `wrong_side_recall` is materially better (that failure mode, F4,
  is the one we most need automated coverage for).
- No candidate passes → run §7 disagreement expansion once, re-measure.
  Still failing → **no judge is deployed**; claim-support stays manual-only
  and Q2 plans that depend on a judge (runtime verifier, scaled
  unsupported_claim_rate) are descoped. This outcome must be reported, not
  worked around.

## 6. Custom Judge Prompt (J-C) — Draft

```text
You are auditing whether cited evidence supports a claim from a
question-answering system. You will see one CLAIM and the full text of its
CITED CHUNKS. Judge only from the cited text. You have no other knowledge:
if the cited text does not contain it, it does not exist.

Rules:
1. supported — every factual element of the claim (entities, numbers,
   conditions) is verifiable from the cited text alone. Paraphrase is fine.
   Numeric values must match exactly.
2. weak — the cited text covers part of the claim, or supporting it requires
   an inference step beyond paraphrase (e.g., combining statements the text
   does not itself connect).
3. unsupported — the cited text does not contain the claim's content, or
   contradicts it.
4. If multiple chunks are cited, judge against their union.
5. When torn between two labels, choose the lower one.
6. wrong_side_citation = true if the cited text discusses a confusably
   similar topic, version, or document that is plausibly NOT what the claim
   is actually about (e.g., the claim concerns path parameters but the cited
   text describes query parameters).

CLAIM:
{claim_text}

CITED CHUNKS:
{cited_chunks_text}

Respond with JSON only:
{"label": "supported|weak|unsupported",
 "wrong_side_citation": true|false,
 "rationale": "<= 2 sentences, quoting the decisive span or its absence"}
```

Few-shot slots: after the human audit lands, insert 2–3 anchored examples
(one per label) drawn from claims **excluded from the agreement measurement**
to avoid contaminating the validation. Prompt changes after selection require
re-running §4 in full (see §8).

## 7. Disagreement-Driven Anchor Expansion

If selection fails or intervals are too wide to act on:

1. Run the best candidate over a wider claim pool (all real-run claims).
2. Sample 20–40 items where candidates disagree with each other or where the
   best candidate's rationale looks shakiest.
3. Human-label them under audit rules (same blinding) and add to the anchor
   set (target 60–80).
4. Re-measure §4 once. Disagreement sampling is deliberately adversarial to
   the judge — agreement measured on it is conservative, which is the
   direction we want to err in.

## 8. Post-Selection Usage Rules

- Every judge-derived metric carries the `judge_based` label in summaries and
  reports; it is never blended with, or substituted for, human-audit numbers.
- Allowed wording: "judge-based unsupported_claim_rate (judge validated at
  X% binary agreement against N human-labeled anchors)". Forbidden: quoting
  judge output as "citation accuracy" or as human-audited support.
- Re-validation triggers (full §4 rerun): judge model change, prompt change,
  corpus domain change, or a scheduled drift check at the next quarter.
- Runtime verifier use (Q2 Phase 3, package decision B) inherits all of the
  above; the verifier threshold (which labels block an answer) is frozen in
  the agent design review, defaulting to: only `supported` passes.

## 9. Cost

Anchor validation: 3 candidates × ≤40 claims × ~2 iterations ≈ 250 calls.
Full-run backfill: a few hundred more. Total well under ¥30. Cost is not a
constraint; discipline is.
