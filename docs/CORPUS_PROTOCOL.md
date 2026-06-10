# Corpus Protocol

The Q1 corpus plan separates synthetic fixtures, public external documents, and
hard negatives so the project can show where the system is grounded and where it
fails.

## Synthetic Fixture Corpus

`data/sample_corpus/` contains minimal generated documents for schema, smoke
test, and local demo checks. Fixture results must not be packaged as headline
metrics.

## Public External Corpus

`data/public_corpus/` is reserved for public-web or public-repository documents.
Public documents must preserve source attribution and license notes where
available.

## Hard Negative Corpus

`data/hard_negative_corpus/` is reserved for documents that look relevant but
should not support the answer. These cases protect against shallow lexical
matching and parametric leakage.

## Metadata Overlay

`data/public_corpus/overlay/` is reserved for project-authored metadata that is
not native to the source. Overlay files should record access level, status,
document type, and evaluation tags without pretending the metadata came from the
original source.

## metadata_origin

`metadata_origin=native` means metadata came from the document or its first-party
source. `metadata_origin=overlay` means this project added the metadata for
evaluation and system control.

## Metric Boundary

Synthetic fixtures are useful for CI and schema checks. They cannot become
formal Q1 headline results. Headline metrics must be based on the approved eval
protocol and real model components.

