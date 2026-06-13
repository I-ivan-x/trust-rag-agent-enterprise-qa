# Citation Support Audit Guide (Manual Audit Protocol v1)

Status: protocol frozen, ready to freeze sample (C1-00 landed; answers
persisted). Audit not yet labeled.
Owner: Project Owner (single annotator).
Prerequisite reading: `docs/CITATION_AUDIT.md` (rule-based v1 status and caveats).

This protocol defines the manual citation-support audit required to close Q1.
Until pass 1 and the re-label pass are complete, no report or resume may state
"citation accuracy X%". The only safe wording remains "structural citation
validity (rule-based v1)".

**Scope is a census, not a sample (revised 2026-06-12).** The protocol was
originally written assuming a 25–40 claim sample drawn from a larger answered
pool. The measured reality is that the fail-closed system answered only ~15
cases across external + obfuscated, and **every answered case produced exactly
one claim** (external 13 → 13 claims, obfuscated 2 → 2 claims, zero multi-claim
cases). There is no larger pool to sample from. The audit therefore covers
**100% of answered cases (n=15)** — a census, which carries no sampling error,
not a deficient sample. The small n is itself a reportable finding: it is the
direct consequence of ~26% external answer coverage under fail-closed gating
(over-refusal), and **must not be padded** with Q2 hard-negative claims.
The re-label pass requires a ≥7-day gap, so pass 1 should start as soon as the
sample is frozen to finish inside Q1.

------

## 0. Execution Prerequisite — Artifact Gap (RESOLVED 2026-06-12)

This blocker is closed. It is kept here as a record because it produced
ADR-008 (trace schema must be derived from what governance consumes).

History: Week 6 artifacts persisted only boolean metrics and decision
metadata, never answer text or claim→citation bindings, so the (claim, cited
chunks) pairs this audit needs were generated at run time and discarded.

Resolution (C1-00, `docs/SPEC_C1_00_ARTIFACT_PERSISTENCE.md`):

1. `RealFinalResult` now carries `claims`, and the runner persists a per-run
   `answers.jsonl` with `answer_text`, `claims[].text`,
   `claims[].supporting_chunk_ids`, `cited_chunk_texts`, and
   `cited_text_sha256`.
2. `final_agentic` re-run on external + obfuscated only:
   `week7-audit-external-final-agentic` and
   `week7-audit-obfuscated-final-agentic`. hard_negative was deliberately
   excluded (metadata-only template queries; deferred to ROADMAP C2-05 / Q2-W1).
3. The audit applies to **these re-run run_ids**. Reports must cite them and
   must not present the audit as auditing the original Week 6 runs (answers are
   regenerated and may differ — expected non-determinism, stated once in the
   report).

The 7-day re-label clock starts from pass 1 of these re-run-based labels.

------

## 1. Audit Unit

The audit unit is one **(claim, cited chunk set)** pair:

- `claim_text`: one claim as emitted by the answer generator
  (`claims[i].text`).
- `citation_chunk_ids`: the `supporting_chunk_ids` bound to that claim.

The judgment is always: *do the cited chunks support this claim*, never
"is the overall answer good".

## 2. Eligible Population

Claims are drawn only from **real-run answers** (measured 2026-06-12 from the
re-run `answers.jsonl`):

| run_id | system | answered cases | claims |
| --- | --- | ---: | ---: |
| `week7-audit-external-final-agentic` | `final_agentic` | 13 / 50 | 13 |
| `week7-audit-obfuscated-final-agentic` | `final_agentic` | 2 / 15 | 2 |
| rewritten hard-negative real run (Q2-W1, post-adjudication) | `final_agentic` | deferred | deferred |
| **census total (Q1)** | | **15** | **15** |

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

## 3. Census Rules (not sampling)

The original 25-floor arithmetic — "13 external cases × 2-claim cap ≈ 26" — is
**empirically disproven**: every answered case produced exactly one claim, so
the 2-claim cap never binds and the real ceiling is 15. There is nothing to
sample; the audit is a census of all 15 answered-case claims.

| stratum | claims (all taken) |
| --- | ---: |
| external | 13 |
| obfuscated | 2 |
| hard_negative (rewritten run, deferred to Q2-W1) | — |
| **Q1 census total** | **15** |

The hard_negative stratum is added only once the rewritten-query real run
exists; its purpose there is the `wrong_side_citation` mechanism (F4), not
hard-negative robustness.

Procedure (deterministic, reproducible):

1. Take **all** answered-case claims from the two re-run `answers.jsonl` files
   (external first, then obfuscated), sorted by `case_id` then `claim_index`.
2. Assign `audit_id` in that order (`AUD-001` …). `random.Random(42)` may be
   used to permute audit_id assignment for reproducibility, but since all 15
   are taken, shuffling changes only numbering, never inclusion.
3. The 2-claim-per-case cap is retained in the rule but is inert at n=15
   (no case has >1 claim); it will matter only if a future re-run yields
   multi-claim answers.
4. Freeze the sample as `data/citation_audit/manual_audit_v1_sample.jsonl`
   **before** any labeling begins. Each row must carry the cited-text snapshot
   and its sha256 (copied from `answers.jsonl`), so later index rebuilds cannot
   silently change what was judged. Verify each row's sha256 matches
   `answers.jsonl`.

## 4. Label Schema

One JSONL row per audit unit, file
`data/citation_audit/manual_audit_v1_labels.jsonl` (this directory is
committed to git; it is a deliverable, unlike `data/eval_runs/`):

```json
{
  "audit_id": "AUD-001",
  "run_id": "week7-audit-external-final-agentic",
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
- Size: at the Q1 census (n=15), re-label **8 items** selected with
  `random.Random(43)` from the labeled set. (For a future larger set: ~half,
  capped at 10.)
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

Report **absolute counts**, not percentages, as the primary form. At n=15 a
percentage implies a precision the census does not have; counts are honest.

```text
supported / weak / unsupported           = absolute counts over the 15 claims
citation_support_accuracy_manual_census  = supported / 15  (report only beside the count)
wrong_side_count                         = wrong_side_citation true (count)
self_consistency_exact / _binary         = from §6 (over 8 re-labeled items)
```

Reporting rules:

- Lead with the per-claim results table (15 rows) and combined counts. The
  obfuscated stratum (n=2) is case study only — never a percentage. The
  external stratum (n=13) may carry a percentage only if shown next to its
  count and labeled census, not sample.
- Frame as a **census**: "complete manual audit of all 15 answered-case
  citations from the real evaluation", not "a sample of 15".
- Results go into `CITATION_AUDIT.md` under a new "Manual Audit Results v1"
  section, replacing the current "audit pending" caveat; `EVALUATION_REPORT.md`
  links to it and may then — and only then — cite the manual support counts.
- Mandatory limitations paragraph: single annotator (self-consistency, not
  inter-annotator reliability); n=15 is small **because** the fail-closed
  system answered only ~26% of external queries — the scarcity is an
  over-refusal finding, not an audit defect, and the audit covers the answered
  set completely (no survivorship within the answered population, but it says
  nothing about the ~74% refused); rule-based `citation_valid=1.0` remains a
  structural metric and is not superseded by this audit.

Allowed wording after completion:

> Complete manual citation-support audit of all 15 answered cases from the
> real evaluation (external 13 + obfuscated 2): A supported, B weak,
> C unsupported (self-consistency: E% exact / F% binary on a one-week re-label
> of 8 items).

Still forbidden, even after completion:

- extrapolating the census rate to "the system's citation accuracy" over all
  queries (it covers answered cases only, not the refused majority);
- mixing structural `citation_valid` with manual support numbers in one claim;
- citing the obfuscated stratum as a percentage.

## 8. Timeline

| step | when |
| --- | --- |
| Freeze sample file (C1-01, 15 rows) | as soon as Owner confirms census scope |
| Pass 1 labeling (~30–45 min for 15 claims) | same day or next |
| Re-label pass (8 items) | ≥7 days later |
| Write results into CITATION_AUDIT.md / EVALUATION_REPORT.md | after re-label |
