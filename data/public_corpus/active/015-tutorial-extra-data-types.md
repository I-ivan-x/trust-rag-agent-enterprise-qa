---
doc_id: doc-public-fastapi-0015-extra-data-types-extra-data-types
title: 'Extra Data Types { #extra-data-types }'
doc_type: public_doc
status: active
version: fastapi-docs-master
created_at: null
updated_at: '2026-06-11'
effective_date: null
owner_team: FastAPI Project
department: Public Documentation
access_level: internal
allowed_roles:
- employee
- engineer
tags:
- fastapi
- 015-tutorial-extra-data-types
language: en
source_path: data/public_corpus/active/015-tutorial-extra-data-types.md
supersedes_doc_id: null
superseded_by: null
conflict_group_id: null
is_authoritative: true
corpus_source: public_external
source_origin: public_repo
source_license_note: FastAPI documentation from the public fastapi/fastapi GitHub
  repository; use subject to the upstream project license.
hard_negative_group_id: null
metadata_origin: native
source_url: https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/extra-data-types.md
upstream_repo_path: docs/en/docs/tutorial/extra-data-types.md
---

# Extra Data Types { #extra-data-types }

Up to now, you have been using common data types, like:

* `int`
* `float`
* `str`
* `bool`

But you can also use more complex data types.

And you will still have the same features as seen up to now:

* Great editor support.
* Data conversion from incoming requests.
* Data conversion for response data.
* Data validation.
* Automatic annotation and documentation.

## Other data types { #other-data-types }

Here are some of the additional data types you can use:

* `UUID`:
    * A standard "Universally Unique Identifier", common as an ID in many databases and systems.
    * In requests and responses will be represented as a `str`.
* `datetime.datetime`:
    * A Python `datetime.datetime`.
    * In requests and responses will be represented as a `str` in ISO 8601 format, like: `2008-09-15T15:53:00+05:00`.
* `datetime.date`:
    * Python `datetime.date`.
    * In requests and responses will be represented as a `str` in ISO 8601 format, like: `2008-09-15`.
* `datetime.time`:
    * A Python `datetime.time`.
    * In requests and responses will be represented as a `str` in ISO 8601 format, like: `14:23:55.003`.
* `datetime.timedelta`:
    * A Python `datetime.timedelta`.
    * In requests and responses will be represented as a `float` of total seconds.
    * Pydantic also allows representing it as a "ISO 8601 time diff encoding", [see the docs for more info](https://docs.pydantic.dev/latest/concepts/serialization/#custom-serializers).
* `frozenset`:
    * In requests and responses, treated the same as a `set`:
        * In requests, a list will be read, eliminating duplicates and converting it to a `set`.
        * In responses, the `set` will be converted to a `list`.
        * The generated schema will specify that the `set` values are unique (using JSON Schema's `uniqueItems`).
* `bytes`:
    * Standard Python `bytes`.
    * In requests and responses will be treated as `str`.
    * The generated schema will specify that it's a `str` with `binary` "format".
* `Decimal`:
    * Standard Python `Decimal`.
    * In requests and responses, handled the same as a `float`.
* You can check all the valid Pydantic data types here: [Pydantic data types](https://docs.pydantic.dev/latest/usage/types/types/).

## Example { #example }

Here's an example *path operation* with parameters using some of the above types.

{* ../../docs_src/extra_data_types/tutorial001_an_py310.py hl[1,3,12:16] *}

Note that the parameters inside the function have their natural data type, and you can, for example, perform normal date manipulations, like:

{* ../../docs_src/extra_data_types/tutorial001_an_py310.py hl[18:19] *}
