# Corpus Protocol

The Q1 corpus is split into three sources so the project can show where the
system is grounded and where it fails. The three sources are reported
separately and must never be blended into a single headline number.

All synthetic fixtures use the fictional company **Northstar Cloud**. No real
company, product, or sensitive information appears in fixtures.

## corpus_source (frozen enum)

Every `DocumentMetadata` carries `corpus_source`:

- `synthetic_fixture` — generated Northstar Cloud documents.
- `public_external` — real public-web / public-repo documents.
- `hard_negative` — near-miss documents that look relevant but should not
  support the answer.

Companion fields (frozen):

- `source_origin`: `generated | public_web | public_repo`
- `source_license_note`: string | null
- `hard_negative_group_id`: string | null
- `metadata_origin`: `native | overlay`

## Synthetic Fixture Corpus

`data/sample_corpus/` holds minimal generated documents for schema checks,
chunking tests, smoke tests, and local demos. Fixtures may be designed to
trigger a specific gate (ACL, deprecated state, active-active conflict,
citation binding, refusal, agentic recovery). In reports they are referred to
only as *controlled fixture evaluation*. **Fixture results are never headline
metrics.**

## Public External Corpus

`data/public_corpus/` holds real public documents, kept verbatim with source
attribution and license notes. Public external eval is the primary basis for
headline metrics. Prefer versioned pages updated within the last 12 months.

## Hard Negative Corpus

`data/hard_negative_corpus/` holds adjacent-version, similar-title, and
same-term/different-answer documents. Of the frozen 30 pairs, at least 20 are
adjacent versions taken from the public corpus; at most 10 are self-authored.

## Public corpus metadata overlay

Public text is never rewritten for gate testing. Only the metadata fields
`status`, `access_level`, `allowed_roles`, `version`, `superseded_by`, and
`conflict_group_id` may be overlaid via
`data/public_corpus/overlay/metadata_overlay.yaml`.

Overlay constraints (frozen): restricted/confidential 15-25%; deprecated
10-15%, applied to versions that genuinely have a newer page; overlay is
seed-controlled and reproducible; any field changed by overlay is marked
`metadata_origin=overlay`. Reports must state that external ACL/state metadata
is a controlled overlay while the text is real public text.

## Metric Boundary

Headline metrics come only from the public external corpus under the approved
eval protocol with real embedding, real reranker, and real LLM. Synthetic
fixtures and any mock run are for CI / schema / smoke only.
