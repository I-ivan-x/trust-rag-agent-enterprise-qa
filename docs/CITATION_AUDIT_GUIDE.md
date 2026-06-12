# Citation Support Audit Guide (Manual Audit Protocol v1)

Status: protocol frozen, audit not yet executed.
Owner: Project Owner (single annotator).
Prerequisite reading: `docs/CITATION_AUDIT.md` (rule-based v1 status and caveats).

This protocol defines the minimum viable manual citation-support audit required
to close Q1. Until pass 1 and the re-label pass are complete, no report or
resume may state "citation accuracy X%". The only safe wording remains
"structural citation validity (rule-based v1)".

Minimum viable scope: 25 claims. Ideal scope: 40 claims.
The re-label pass requires a ≥7-day gap, so pass 1 must start at the beginning
of Week 7 to finish inside Q1.

------

## 0. Execution Prerequisite — Artifact Gap (verified 2026-06-12)

Sample freezing is currently **blocked**. Inspection of all three target runs
confirmed that no Week 6 artifact persists the generated answer text, the
claims, or the claim→citation bindings:

- `results.jsonl`: boolean metrics only;
- `traces.jsonl`: retrieval ids and decision metadata; the `answer` event
  carries flags (`answer_llm_called`, `response_mode`) but no answer content;
- `failures.jsonl` / `citation_audit_sample.jsonl`: no claim text either.

The (claim, cited chunks) pairs this audit needs were produced at run time and
discarded. They cannot be reconstructed without re-calling the LLM, and they
must not be fabricated.

Required unblock steps (small, cheap):

1. Codex: persist `answer_text`, `claims[].text`, and
   `claims[].supporting_chunk_ids` in run artifacts (results or a dedicated
   `answers.jsonl` per run).
2. Re-run `final_agentic` real on external + obfuscated only (≈65 LLM calls,
   roughly ¥5). The hard_negative split is deliberately excluded: its Week 6
   queries are metadata-only templates (see HARD_NEGATIVE_ADJUDICATION.md),
   so claims answered to them carry no hard-negative semantics. That stratum
   is deferred until the rewritten-query real run lands (ROADMAP C2-05 /
   Q2-W1).
3. The audit then applies to the **re-run's run_ids**. Reports must cite those
   run_ids; the audit must not be presented as auditing the original Week 6
   runs (answers are regenerated and may differ — that is expected
   non-determinism, not a defect, and must be stated once in the report).

Timeline impact: "Week 7 day 1" in §8 becomes "the day the re-run lands".
The 7-day re-label clock starts from pass 1 of the re-run-based labels.

------

## 1. Audit Unit

The audit unit is one **(claim, cited chunk set)** pair:

- `claim_text`: one claim as emitted by the answer generator
  (`claims[i].text`).
- `citation_chunk_ids`: the `supporting_chunk_ids` bound to that claim.

The judgment is always: *do the cited chunks support this claim*, never
"is the overall answer good".

## 2. Eligible Population

Claims are drawn only from **real-run answers**:

| run_id | system sampled | answered cases available |
| --- | --- | --- |
| `week6-real-external-full` | `final_agentic` only | ~13 (refusal_rate 0.74) |
| `week6-real-obfuscated-full` | `final_agentic` only | ~2 (13/15 refused) |
| rewritten hard-negative real run (Q2-W1, post-adjudication) | `final_agentic` | ~18 — deferred stratum |

Exclusions, with reasons recorded here once so the report can reference them:

- `direct_llm` rows: no retrieved citations by design; auditing them measures
  nothing about citation support.
- `final_gated` rows: identical results to `final_agentic` in Week 6 runs;
  including both would double-count the same answers.
- `week6-fixture-functional-regression`: mock run, zero LLM calls; its
  "citations" are not real model output.

Deviation from plan §7.2: the plan allocated `external 20 + hard_negative 10 +
fixture 10`. The fixture stratum is replaced because the Week 6 fixture run was
mock-only. Replacement allocation is defined in §3. This deviation must be
declared in `CITATION_AUDIT.md` when results are written.

## 3. Sampling Rules

Target strata (ideal 40 / minimum 25):

| stratum | ideal | minimum |
| --- | ---: | ---: |
| external | 24 | 21 |
| hard_negative (rewritten run, deferred) | 12 | 0 — not required for the 25-claim minimum |
| obfuscated | all available (~4) | all available (~2) |

The 25-claim minimum is reachable from external + obfuscated alone
(13 answered external cases × 2-claim cap ≈ 26 claims). The hard_negative
stratum is added once the rewritten-query real run exists; its purpose there
is the `wrong_side_citation` mechanism (F4), not hard-negative robustness.

Procedure (deterministic, reproducible):

1. List answered cases per stratum, sorted by `case_id`.
2. Shuffle with `random.Random(42)`.
3. Walk the shuffled list, taking claims in claim-index order, with a cap of
   **2 claims per case**, until the stratum target is reached.
4. If a stratum has fewer available claims than its target (expected for
   obfuscated), take all of them and reallocate the shortfall to
   hard_negative first, then external. Record the actual counts.
5. Freeze the sample as `data/citation_audit/manual_audit_v1_sample.jsonl`
   **before** any labeling begins. The sample file must include a snapshot of
   each cited chunk's text (or a content hash plus path), so later index
   rebuilds cannot silently change what was judged.

## 4. Label Schema

One JSONL row per audit unit, file
`data/citation_audit/manual_audit_v1_labels.jsonl` (this directory is
committed to git; it is a deliverable, unlike `data/eval_runs/`):

```json
{
  "audit_id": "AUD-001",
  "run_id": "week6-real-external-full",
  "case_id": "external-012",
  "system": "final_agentic",
  "eval_split": "external",
  "claim_index": 0,
  "claim_text": "...",
  "citation_chunk_ids": ["..."],
  "cited_text_snapshot_sha256": ["..."],
  "label": "supported | weak | unsupported",
  "wrong_side_citation": false,
  "notes": "free text, required when label != supported",
  "pass": "initial",
  "labeled_at": "2026-06-15"
}
```

## 5. Decision Rules

Three-way label, per plan §7.2:

- **supported**: every factual element of the claim (entities, numbers,
  conditions) is verifiable from the cited chunk text alone. Paraphrase is
  fine; numeric values must match exactly.
- **weak**: the cited text covers part of the claim, or supporting it requires
  an inference step beyond paraphrase (e.g. combining two statements the chunk
  does not itself connect).
- **unsupported**: the cited text does not contain the claim's content, or
  contradicts it.

Additional boolean, hard-negative oriented:

- **wrong_side_citation**: the cited text does support the claim's wording,
  but the chunk comes from the wrong document of a hard-negative pair, the
  wrong version, or a non-gold conflict-group member. This is how we catch
  "structurally valid, semantically wrong evidence" — the F4 failure mode.

Hard rules:

1. Judge only the frozen cited-text snapshot. Never open the full document to
   "find" support the citation did not give.
2. No external/world knowledge may rescue a claim.
3. If multiple chunks are cited, the claim is supported if their union
   supports it.
4. When torn between two labels, choose the lower one and write a note.

## 6. Re-label Pass (Self-Consistency)

- Timing: **≥7 days** after pass 1 completes.
- Size: 10 items if pass 1 had 40; 8 items if pass 1 had 25. Selected with
  `random.Random(43)` from the labeled set.
- Blinding: re-label from the sample file (claim + cited text only), without
  the pass-1 label visible. Write rows with `"pass": "relabel"` to
  `data/citation_audit/manual_audit_v1_relabel.jsonl`.
- Self-consistency metrics:
  - `exact_agreement` = identical 3-way label / n_relabeled;
  - `binary_agreement` = agreement after collapsing to
    supported vs (weak + unsupported).
- With a single annotator this measures self-consistency, not inter-annotator
  reliability. The report must say so.

## 7. Reporting

Metrics to compute over pass-1 labels:

```text
citation_support_accuracy_manual_sampled = supported / n
citation_support_or_weak_rate            = (supported + weak) / n
unsupported_rate                         = unsupported / n
wrong_side_rate (hard_negative stratum)  = wrong_side_citation true / n_stratum
self_consistency_exact / _binary         = from §6
```

Reporting rules:

- Per-stratum breakdown; any stratum with n < 5 (expected: obfuscated) is
  reported as case studies only, no percentage — same rule as the eval report.
- Results go into `CITATION_AUDIT.md` under a new "Manual Audit Results v1"
  section, replacing the current "audit pending" caveat; `EVALUATION_REPORT.md`
  links to it and may then — and only then — cite
  `citation_support_accuracy_manual_sampled`.
- Mandatory limitations paragraph: single annotator; small n; sample drawn only
  from answered cases (survivorship — the fail-closed system answered ~26% of
  external queries, so this audits the surviving answers, not hypothetical
  coverage); rule-based `citation_valid=1.0` remains a structural metric and is
  not superseded by this audit.

Allowed wording after completion:

> Manual citation-support audit on N sampled claims from real runs:
> X% supported, Y% weak, Z% unsupported (self-consistency: E% exact / B%
> binary on a one-week re-label of M items).

Still forbidden, even after completion:

- extrapolating the sampled rate to "the system's citation accuracy";
- mixing structural `citation_valid` with manual support numbers in one claim;
- citing the obfuscated stratum as a percentage.

## 8. Timeline

| step | when |
| --- | --- |
| Freeze sample file | Week 7, day 1 |
| Pass 1 labeling (~2h for 40 claims) | Week 7, days 1–2 |
| Re-label pass | Week 8 (≥7 days later) |
| Write results into CITATION_AUDIT.md / EVALUATION_REPORT.md | Week 8 |
