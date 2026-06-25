---
doc_id: doc-public-fastapi-0016-cookie-parameters-cookie-parameters
title: 'Cookie Parameters { #cookie-parameters }'
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
- 016-tutorial-cookie-params
language: en
source_path: data/public_corpus/active/016-tutorial-cookie-params.md
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
source_url: https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/cookie-params.md
upstream_repo_path: docs/en/docs/tutorial/cookie-params.md
---

# Cookie Parameters { #cookie-parameters }

You can define Cookie parameters the same way you define `Query` and `Path` parameters.

## Import `Cookie` { #import-cookie }

First import `Cookie`:

{* ../../docs_src/cookie_params/tutorial001_an_py310.py hl[3] *}

## Declare `Cookie` parameters { #declare-cookie-parameters }

Then declare the cookie parameters using the same structure as with `Path` and `Query`.

You can define the default value as well as all the extra validation or annotation parameters:

{* ../../docs_src/cookie_params/tutorial001_an_py310.py hl[9] *}

/// note | Technical Details

`Cookie` is a "sister" class of `Path` and `Query`. It also inherits from the same common `Param` class.

But remember that when you import `Query`, `Path`, `Cookie` and others from `fastapi`, those are actually functions that return special classes.

///

/// note

To declare cookies, you need to use `Cookie`, because otherwise the parameters would be interpreted as query parameters.

///

/// note

Have in mind that, as **browsers handle cookies** in special ways and behind the scenes, they **don't** easily allow **JavaScript** to touch them.

If you go to the **API docs UI** at `/docs` you will be able to see the **documentation** for cookies for your *path operations*.

But even if you **fill the data** and click "Execute", because the docs UI works with **JavaScript**, the cookies won't be sent, and you will see an **error** message as if you didn't write any values.

///

## Recap { #recap }

Declare cookies with `Cookie`, using the same common pattern as `Query` and `Path`.
