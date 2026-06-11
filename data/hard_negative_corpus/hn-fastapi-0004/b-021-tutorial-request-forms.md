---
doc_id: hard-negative-hn-fastapi-0004-b
title: 'Hard Negative HN-FASTAPI-0004 B: Form Data { #form-data }'
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
- 021-tutorial-request-forms
language: en
source_path: data/hard_negative_corpus/hn-fastapi-0004/b-021-tutorial-request-forms.md
supersedes_doc_id: null
superseded_by: null
conflict_group_id: null
is_authoritative: true
corpus_source: hard_negative
source_origin: public_repo
source_license_note: FastAPI documentation from the public fastapi/fastapi GitHub
  repository; use subject to the upstream project license.
hard_negative_group_id: hn-fastapi-0004
metadata_origin: native
source_url: https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/request-forms.md
upstream_repo_path: docs/en/docs/tutorial/request-forms.md
---

# Form Data { #form-data }

When you need to receive form fields instead of JSON, you can use `Form`.

/// note

To use forms, first install [`python-multipart`](https://github.com/Kludex/python-multipart).

Make sure you create a [virtual environment](../virtual-environments.md), activate it, and then install it, for example:

```console
$ pip install python-multipart
```

///

## Import `Form` { #import-form }

Import `Form` from `fastapi`:

{* ../../docs_src/request_forms/tutorial001_an_py310.py hl[3] *}

## Define `Form` parameters { #define-form-parameters }

Create form parameters the same way you would for `Body` or `Query`:

{* ../../docs_src/request_forms/tutorial001_an_py310.py hl[9] *}

For example, in one of the ways the OAuth2 specification can be used (called "password flow") it is required to send a `username` and `password` as form fields.

The <dfn title="specification">spec</dfn> requires the fields to be exactly named `username` and `password`, and to be sent as form fields, not JSON.

With `Form` you can declare the same configurations as with `Body` (and `Query`, `Path`, `Cookie`), including validation, examples, an alias (e.g. `user-name` instead of `username`), etc.

/// note

`Form` is a class that inherits directly from `Body`.

///

/// tip

To declare form bodies, you need to use `Form` explicitly, because without it the parameters would be interpreted as query parameters or body (JSON) parameters.

///

## About "Form Fields" { #about-form-fields }

The way HTML forms (`<form></form>`) sends the data to the server normally uses a "special" encoding for that data, it's different from JSON.

**FastAPI** will make sure to read that data from the right place instead of JSON.

/// note | Technical Details

Data from forms is normally encoded using the "media type" `application/x-www-form-urlencoded`.

But when the form includes files, it is encoded as `multipart/form-data`. You'll read about handling files in the next chapter.

If you want to read more about these encodings and form fields, head to the [<abbr title="Mozilla Developer Network">MDN</abbr> web docs for `POST`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods/POST).

///

/// warning

You can declare multiple `Form` parameters in a *path operation*, but you can't also declare `Body` fields that you expect to receive as JSON, as the request will have the body encoded using `application/x-www-form-urlencoded` instead of `application/json`.

This is not a limitation of **FastAPI**, it's part of the HTTP protocol.

///

## Recap { #recap }

Use `Form` to declare form data input parameters.
