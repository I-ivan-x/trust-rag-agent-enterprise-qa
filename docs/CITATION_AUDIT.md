# Citation Audit

Rule-based v1 audit sample. This is not a human adjudication file.

Week 6 real runs populate audit rows from real LLM answers bound to real
retrieved chunks. Refused cases contribute no answer citations by design; the
summary metric treats correct trust-gated refusals as citation-valid.

## Rule-Based Audit Samples

| run_id | sample_rows | raw_invalid_rows | note |
| --- | ---: | ---: | --- |
| `week6-real-external-full` | 25 | 19 | sample contained `direct_llm` rows; direct_llm has no retrieved citations by design |
| `week6-real-obfuscated-full` | 25 | 15 | raw invalid rows are dominated by refused final-system cases with no answer citations |
| `week6-hard-negative-final-agentic-real` | 20 | 0 | final_agentic produced citation-bound answers, but retrieval selected the wrong hard-negative evidence |

The final-system summary metrics report structural citation validity, not a
human citation-support accuracy claim. A citation can be structurally valid
while still pointing to evidence for the wrong hard-negative side.

## Manual Audit Results v1 — human census (2026-06-14)

Attribution note: an earlier table here reported these counts as a "manual
census", but those pass-1 labels were produced by **GPT**, not a human. That is
corrected. There are now two passes:

- **Human census (primary)** — `manual_audit_v1_labels.jsonl` (annotator=owner).
  The Owner labeled all 15 answered-case claims **blind** (without seeing the
  GPT labels). This is the Q1 manual citation-support audit.
- **GPT judge pass (preview)** — `judge_pass_v1_gpt_labels.jsonl` (annotator=gpt).
  An LLM-judge signal reused as an early human-vs-judge data point for Phase 2.

Census scope: all 15 answered-case claims from the real evaluation
(external 13 + obfuscated 2; runs `week7-audit-external-final-agentic`,
`week7-audit-obfuscated-final-agentic`). hard_negative deferred (metadata-only
template queries; ROADMAP C2-05).

### Human result

| label | count (of 15) |
| --- | ---: |
| supported | 11 |
| weak | 4 (AUD-005, 010, 012, 015) |
| unsupported | 0 |
| wrong_side_citation | 0 |

Finding: across every answered case, **zero unsupported and zero wrong-side
citations**, human-verified. All 4 `weak` labels are claim-extraction
artifacts — two are the sentence fragment "The same way you use `Body`,
`Query`, etc." (AUD-005, 010) and two are the filler/transitional sentence
"Now let's go back a bit and understand what is all that." (AUD-012, 015) —
emitted as standalone claims. These are an answer-generator claim-segmentation
issue (a Q2 input), not a citation-binding or retrieval failure: the cited
chunks are correct; the *claim text* selected is degenerate.

### Human-vs-GPT agreement (NOT self-consistency)

Exact agreement: **15/15 (100%)**, zero disagreements, including the same 4
`weak` items. Binary (supported vs not): 15/15.

**This must not be over-read.** It is inter-annotator (human vs LLM) agreement,
not self-consistency, and the agreement is inflated by an easy task: 11 of 15
cited snapshots contain the claim sentence near-verbatim, and the 4 weak cases
are objectively degenerate claim strings. 100% on n=15 easy items has a wide
confidence interval and says **nothing** about agreement on hard judgments
(e.g. hard-negative wrong-side calls) — which is exactly what Phase 2 must test
on harder anchors. It is an encouraging but limited early signal that the GPT
judge tracked the human on this split.

### Status

Human census complete. True human self-consistency (Owner vs a ≥7-day blind
re-label) is now **optional**, not a Q1 blocker, because a one-pass human
census exists; on this easy split it would likely also be ~100% (low
information). Phase 2 judge selection uses the 15 human labels as the anchor
set and is governed by the absolute gate G2 (≥0.80), since G1 (anchored to
human self-consistency) is not separately estimated.

### Honesty guardrails (carry into any report or resume)

- Census of **answered** cases only (n=15) — says nothing about the ~74% of
  external queries the fail-closed system refused. The small n is itself an
  over-refusal finding, not an audit defect.
- Report absolute counts, not percentages (n=15). The obfuscated stratum (n=2)
  is case-study only.
- The human-vs-GPT 100% is an LLM-judge preview on an easy split, not a
  validated judge and not a citation-accuracy claim.
- Rule-based `citation_valid=1.0` remains a structural metric; neither pass
  supersedes or merges with it.

Safe wording: "Blind human audit of all 15 answered-case citations: 11
supported, 4 weak (degenerate claim strings), 0 unsupported, 0 wrong-side; a
GPT judge pass matched the human on all 15 (easy split, n=15, not a validated
judge)."

### Prior status (rule-based v1) — retained

Current citation audit is rule-based v1. It is not an artificial or manual
audit, and `citation_validity` is not the same as human citation support
accuracy. Rule-based v1 `citation_validity` is structural; before the manual
audit it was the only available signal, and it is now complemented (not
replaced) by the census above.

## Manual Review Checklist

- Does each cited chunk actually support the user-facing answer?
- Does a hard-negative answer cite the wrong paired document?
- Was a refusal appropriate given the retrieved evidence?
- Did permission, deprecated, or conflict policy suppress an otherwise
  answerable request?
