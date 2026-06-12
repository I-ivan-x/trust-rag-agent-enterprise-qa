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

## Manual Citation Support Audit Status

Current citation audit is rule-based v1. It is not an artificial or manual
audit, and `citation_validity` is not the same as human citation support
accuracy.

Q1 closeout still needs:

- at least 25 manually reviewed citation-support examples;
- ideally 40 manually reviewed examples;
- a one-week-later re-label pass to estimate self-consistency.

Until that audit exists, reports must not claim "citation accuracy X%" as a
final human conclusion. The safe wording is "citation structure validity" or
"rule-based citation support", paired with the caveat that manual support
review remains open.

## Manual Review Checklist

- Does each cited chunk actually support the user-facing answer?
- Does a hard-negative answer cite the wrong paired document?
- Was a refusal appropriate given the retrieved evidence?
- Did permission, deprecated, or conflict policy suppress an otherwise
  answerable request?
