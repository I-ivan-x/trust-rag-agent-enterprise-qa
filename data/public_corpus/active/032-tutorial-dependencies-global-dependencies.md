---
doc_id: doc-public-fastapi-0032-global-dependencies-global-dependencies
title: 'Global Dependencies { #global-dependencies }'
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
- 032-tutorial-dependencies-global-dependencies
language: en
source_path: data/public_corpus/active/032-tutorial-dependencies-global-dependencies.md
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
source_url: https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/dependencies/global-dependencies.md
upstream_repo_path: docs/en/docs/tutorial/dependencies/global-dependencies.md
---

# Global Dependencies { #global-dependencies }

For some types of applications you might want to add dependencies to the whole application.

Similar to the way you can [add `dependencies` to the *path operation decorators*](dependencies-in-path-operation-decorators.md), you can add them to the `FastAPI` application.

In that case, they will be applied to all the *path operations* in the application:

{* ../../docs_src/dependencies/tutorial012_an_py310.py hl[17] *}


And all the ideas in the section about [adding `dependencies` to the *path operation decorators*](dependencies-in-path-operation-decorators.md) still apply, but in this case, to all of the *path operations* in the app.

## Dependencies for groups of *path operations* { #dependencies-for-groups-of-path-operations }

Later, when reading about how to structure bigger applications ([Bigger Applications - Multiple Files](../../tutorial/bigger-applications.md)), possibly with multiple files, you will learn how to declare a single `dependencies` parameter for a group of *path operations*.
