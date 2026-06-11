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

Week 5A uses a FastAPI documentation subset fetched from the public
`fastapi/fastapi` GitHub repository. The document body text is real public
documentation text. Front matter is generated locally to preserve stable IDs,
source URLs, source repo paths, license notes, language, and Q1 schema fields.

`data/public_corpus/public_corpus_manifest.jsonl` is the eval-author-facing
view. Eval authors may inspect title, tags, section titles, status, access
level, source URL, and metadata origin from the manifest, but should not read
the full document body while drafting external eval queries.

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

`metadata_origin=native` means the parsed document retained its source/front
matter metadata after ingestion. `metadata_origin=overlay` means the public
text is unchanged but at least one controlled metadata field was modified by the
overlay. Week 5A target ratios are 15-25% restricted/confidential and 10-15%
deprecated.

Week 5A FastAPI docs are a single-version public source. Deprecated status and
`superseded_by` values in the overlay are controlled synthetic relationships for
trust-gate testing, not upstream FastAPI version lineage. The public manifest
marks these rows with `overlay_relation_note`.

## Hard Negative Reporting

`data/hard_negative_corpus/hard_negative_manifest.jsonl` records near-miss
pairs separately with `hard_negative_group_id`, pair type, source paths, and
why the pair is hard. Hard negative results must be reported separately from
headline public-external metrics.

Week 5A hard negative pair labels are intentionally conservative. The builder
uses only labels that the current public docs actually support, such as
`adjacent_topic` and `similar_title`; it does not claim adjacent-version,
deprecated-vs-active, same-limit, or meeting-note contrasts unless those source
types are truly present.

## Metric Boundary

Headline metrics come only from the public external corpus under the approved
eval protocol with real embedding, real reranker, and real LLM. Synthetic
fixtures and any mock run are for CI / schema / smoke only.
