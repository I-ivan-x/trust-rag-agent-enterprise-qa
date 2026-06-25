---
doc_id: doc-public-fastapi-0023-request-forms-and-files-request-forms-and-files
title: 'Request Forms and Files { #request-forms-and-files }'
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
- 023-tutorial-request-forms-and-files
language: en
source_path: data/public_corpus/active/023-tutorial-request-forms-and-files.md
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
source_url: https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/request-forms-and-files.md
upstream_repo_path: docs/en/docs/tutorial/request-forms-and-files.md
---

# Request Forms and Files { #request-forms-and-files }

You can define files and form fields at the same time using `File` and `Form`.

/// note

To receive uploaded files and/or form data, first install [`python-multipart`](https://github.com/Kludex/python-multipart).

Make sure you create a [virtual environment](../virtual-environments.md), activate it, and then install it, for example:

```console
$ pip install python-multipart
```

///

## Import `File` and `Form` { #import-file-and-form }

{* ../../docs_src/request_forms_and_files/tutorial001_an_py310.py hl[3] *}

## Define `File` and `Form` parameters { #define-file-and-form-parameters }

Create file and form parameters the same way you would for `Body` or `Query`:

{* ../../docs_src/request_forms_and_files/tutorial001_an_py310.py hl[10:12] *}

The files and form fields will be uploaded as form data and you will receive the files and form fields.

And you can declare some of the files as `bytes` and some as `UploadFile`.

/// warning

You can declare multiple `File` and `Form` parameters in a *path operation*, but you can't also declare `Body` fields that you expect to receive as JSON, as the request will have the body encoded using `multipart/form-data` instead of `application/json`.

This is not a limitation of **FastAPI**, it's part of the HTTP protocol.

///

## Recap { #recap }

Use `File` and `Form` together when you need to receive data and files in the same request.
