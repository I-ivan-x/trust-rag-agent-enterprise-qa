# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingest.loader import load_corpus
from app.ingest.metadata_overlay import apply_metadata_overlay, load_metadata_overlay
from app.ingest.parser_markdown import parse_markdown_document

FASTAPI_REPO = "fastapi/fastapi"
FASTAPI_REF = "master"
DOCS_PREFIX = "docs/en/docs/"
TREE_URL = f"https://api.github.com/repos/{FASTAPI_REPO}/git/trees/{FASTAPI_REF}?recursive=1"
RAW_BASE_URL = f"https://raw.githubusercontent.com/{FASTAPI_REPO}/{FASTAPI_REF}/"
LICENSE_NOTE = (
    "FastAPI documentation from the public fastapi/fastapi GitHub repository; "
    "use subject to the upstream project license."
)
FASTAPI_DOC_PATHS = [
    "docs/en/docs/index.md",
    "docs/en/docs/features.md",
    "docs/en/docs/alternatives.md",
    "docs/en/docs/tutorial/index.md",
    "docs/en/docs/tutorial/first-steps.md",
    "docs/en/docs/tutorial/path-params.md",
    "docs/en/docs/tutorial/query-params.md",
    "docs/en/docs/tutorial/body.md",
    "docs/en/docs/tutorial/query-params-str-validations.md",
    "docs/en/docs/tutorial/path-params-numeric-validations.md",
    "docs/en/docs/tutorial/body-multiple-params.md",
    "docs/en/docs/tutorial/body-fields.md",
    "docs/en/docs/tutorial/body-nested-models.md",
    "docs/en/docs/tutorial/schema-extra-example.md",
    "docs/en/docs/tutorial/extra-data-types.md",
    "docs/en/docs/tutorial/cookie-params.md",
    "docs/en/docs/tutorial/header-params.md",
    "docs/en/docs/tutorial/response-model.md",
    "docs/en/docs/tutorial/extra-models.md",
    "docs/en/docs/tutorial/response-status-code.md",
    "docs/en/docs/tutorial/request-forms.md",
    "docs/en/docs/tutorial/request-files.md",
    "docs/en/docs/tutorial/request-forms-and-files.md",
    "docs/en/docs/tutorial/handling-errors.md",
    "docs/en/docs/tutorial/path-operation-configuration.md",
    "docs/en/docs/tutorial/encoder.md",
    "docs/en/docs/tutorial/body-updates.md",
    "docs/en/docs/tutorial/dependencies/index.md",
    "docs/en/docs/tutorial/dependencies/classes-as-dependencies.md",
    "docs/en/docs/tutorial/dependencies/sub-dependencies.md",
    "docs/en/docs/tutorial/dependencies/dependencies-in-path-operation-decorators.md",
    "docs/en/docs/tutorial/dependencies/global-dependencies.md",
    "docs/en/docs/tutorial/dependencies/dependencies-with-yield.md",
    "docs/en/docs/tutorial/security/index.md",
    "docs/en/docs/tutorial/security/first-steps.md",
    "docs/en/docs/tutorial/security/get-current-user.md",
    "docs/en/docs/tutorial/security/simple-oauth2.md",
    "docs/en/docs/tutorial/security/oauth2-jwt.md",
    "docs/en/docs/tutorial/middleware.md",
    "docs/en/docs/tutorial/cors.md",
    "docs/en/docs/tutorial/sql-databases.md",
    "docs/en/docs/tutorial/bigger-applications.md",
    "docs/en/docs/tutorial/background-tasks.md",
    "docs/en/docs/tutorial/metadata.md",
    "docs/en/docs/tutorial/static-files.md",
    "docs/en/docs/tutorial/testing.md",
    "docs/en/docs/advanced/index.md",
    "docs/en/docs/advanced/path-operation-advanced-configuration.md",
    "docs/en/docs/advanced/additional-status-codes.md",
    "docs/en/docs/advanced/response-directly.md",
    "docs/en/docs/advanced/custom-response.md",
    "docs/en/docs/advanced/additional-responses.md",
]


def fetch_public_corpus(limit: int, output_dir: Path) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_paths = _select_doc_paths(limit)
    written_docs = []
    restricted_count = max(1, round(limit * 0.10))
    confidential_count = max(1, round(limit * 0.10))
    deprecated_count = max(1, round(limit * 0.125))

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for index, repo_path in enumerate(selected_paths):
            raw_url = RAW_BASE_URL + repo_path
            response = client.get(raw_url)
            response.raise_for_status()
            body = _strip_front_matter(response.text)
            target_rel = _target_relative_path(
                repo_path,
                index=index,
                restricted_count=restricted_count,
                confidential_count=confidential_count,
                deprecated_count=deprecated_count,
            )
            target_path = output_dir / target_rel
            title = _title_from_markdown(body) or _title_from_repo_path(repo_path)
            front_matter = _front_matter(
                repo_path=repo_path,
                target_path=target_path,
                target_rel=target_rel,
                title=title,
                raw_url=raw_url,
                index=index,
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                "---\n"
                + yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True)
                + "---\n\n"
                + body.strip()
                + "\n",
                encoding="utf-8",
            )
            written_docs.append(target_path)

    overlay_path = _write_overlay(
        output_dir=output_dir,
        written_docs=written_docs,
        restricted_count=restricted_count,
        confidential_count=confidential_count,
        deprecated_count=deprecated_count,
    )
    manifest_path = write_public_manifest(output_dir, overlay_path)
    return {
        "source": f"https://github.com/{FASTAPI_REPO}/tree/{FASTAPI_REF}/{DOCS_PREFIX}",
        "public_docs": len(written_docs),
        "output_dir": output_dir.as_posix(),
        "overlay_path": overlay_path.as_posix(),
        "public_corpus_manifest_path": manifest_path.as_posix(),
        "warnings": [],
    }


def write_public_manifest(corpus_dir: Path, overlay_path: Path | None) -> Path:
    overlay = load_metadata_overlay(overlay_path)
    raw_documents = load_corpus(corpus_dir)
    parsed_documents = [parse_markdown_document(raw_doc) for raw_doc in raw_documents]
    apply_metadata_overlay(parsed_documents, overlay, corpus_root=corpus_dir)
    records = []
    for parsed_doc in parsed_documents:
        metadata = parsed_doc.metadata
        records.append(
            {
                "doc_id": metadata.doc_id,
                "title": metadata.title,
                "source_url": metadata.source_url,
                "source_origin": metadata.source_origin.value,
                "source_license_note": metadata.source_license_note,
                "source_path": metadata.source_path,
                "doc_type": metadata.doc_type.value,
                "status": metadata.status.value,
                "access_level": metadata.access_level.value,
                "metadata_origin": metadata.metadata_origin.value,
                "tags": metadata.tags,
                "superseded_by": metadata.superseded_by,
                "overlay_relation_note": _overlay_relation_note(metadata),
                "section_titles": _section_titles(parsed_doc.sections),
            }
        )
    manifest_path = corpus_dir / "public_corpus_manifest.jsonl"
    _write_jsonl(manifest_path, records)
    return manifest_path


def _select_doc_paths(limit: int) -> list[str]:
    if len(FASTAPI_DOC_PATHS) >= limit:
        return FASTAPI_DOC_PATHS[:limit]
    response = httpx.get(TREE_URL, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    candidates = sorted(
        item["path"]
        for item in payload.get("tree", [])
        if item.get("type") == "blob"
        and item.get("path", "").startswith(DOCS_PREFIX)
        and item.get("path", "").endswith(".md")
        and "release-notes" not in item.get("path", "")
    )
    if len(candidates) < limit:
        raise RuntimeError(
            f"Only found {len(candidates)} FastAPI docs candidates, need {limit}."
        )
    return candidates[:limit]


def _target_relative_path(
    repo_path: str,
    *,
    index: int,
    restricted_count: int,
    confidential_count: int,
    deprecated_count: int,
) -> Path:
    slug = _slugify(repo_path.removeprefix(DOCS_PREFIX).removesuffix(".md"))
    filename = f"{index + 1:03d}-{slug}.md"
    if index < restricted_count:
        return Path("security") / filename
    if index < restricted_count + confidential_count:
        return Path("confidential") / filename
    if index < restricted_count + confidential_count + deprecated_count:
        return Path("deprecated") / filename
    return Path("active") / filename


def _front_matter(
    *,
    repo_path: str,
    target_path: Path,
    target_rel: Path,
    title: str,
    raw_url: str,
    index: int,
) -> dict[str, Any]:
    today = date.today().isoformat()
    tags = [
        part
        for part in target_rel.with_suffix("").parts
        if part not in {"active", "security", "confidential", "deprecated"}
    ][:5]
    return {
        "doc_id": f"doc-public-fastapi-{index + 1:04d}-{_slugify(title)[:48]}",
        "title": title,
        "doc_type": "public_doc",
        "status": "active",
        "version": "fastapi-docs-master",
        "created_at": None,
        "updated_at": today,
        "effective_date": None,
        "owner_team": "FastAPI Project",
        "department": "Public Documentation",
        "access_level": "internal",
        "allowed_roles": ["employee", "engineer"],
        "tags": ["fastapi", *tags],
        "language": "en",
        "source_path": target_path.as_posix(),
        "supersedes_doc_id": None,
        "superseded_by": None,
        "conflict_group_id": None,
        "is_authoritative": True,
        "corpus_source": "public_external",
        "source_origin": "public_repo",
        "source_license_note": LICENSE_NOTE,
        "hard_negative_group_id": None,
        "metadata_origin": "native",
        "source_url": raw_url,
        "upstream_repo_path": repo_path,
    }


def _write_overlay(
    *,
    output_dir: Path,
    written_docs: list[Path],
    restricted_count: int,
    confidential_count: int,
    deprecated_count: int,
) -> Path:
    deprecated_paths = [
        path.relative_to(output_dir).as_posix()
        for path in written_docs[restricted_count + confidential_count :][:deprecated_count]
    ]
    active_paths = [
        path.relative_to(output_dir).as_posix()
        for path in written_docs[restricted_count + confidential_count + deprecated_count :]
    ]
    document_overrides = []
    for index, deprecated_path in enumerate(deprecated_paths):
        superseded_by = active_paths[index % len(active_paths)] if active_paths else None
        document_overrides.append(
            {
                "path": deprecated_path,
                "status": "deprecated",
                "version": "fastapi-docs-legacy",
                "superseded_by": superseded_by,
            }
        )
    overlay = {
        "seed": 42,
        "relation_note": (
            "Deprecated and superseded_by values are controlled synthetic overlay "
            "relationships for trust-gate testing; they are not upstream FastAPI "
            "version lineage."
        ),
        "defaults": {
            "status": "active",
            "access_level": "internal",
            "allowed_roles": ["employee", "engineer"],
        },
        "rules": [
            {
                "match": "security/**",
                "access_level": "restricted",
                "allowed_roles": ["security_admin"],
            },
            {
                "match": "confidential/**",
                "access_level": "confidential",
                "allowed_roles": ["engineer", "manager"],
            },
            {
                "match": "deprecated/**",
                "status": "deprecated",
            },
        ],
        "documents": document_overrides,
    }
    overlay_path = output_dir / "overlay" / "metadata_overlay.yaml"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.write_text(
        yaml.safe_dump(overlay, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return overlay_path


def _strip_front_matter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", maxsplit=2)
    return parts[2] if len(parts) == 3 else text


def _title_from_markdown(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _title_from_repo_path(repo_path: str) -> str:
    return repo_path.removeprefix(DOCS_PREFIX).removesuffix(".md").replace("/", " - ").title()


def _section_titles(sections) -> list[str]:
    titles = []
    for section in sections:
        titles.append(section.title)
        titles.extend(_section_titles(section.children))
    return titles


def _overlay_relation_note(metadata) -> str | None:
    if metadata.status.value == "deprecated" and metadata.superseded_by:
        return (
            "Controlled synthetic overlay relation for trust-gate testing; "
            "not an upstream FastAPI version chain."
        )
    return None


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "doc"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Week 5A public FastAPI corpus.")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--output", type=Path, default=Path("data/public_corpus"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = fetch_public_corpus(limit=args.limit, output_dir=args.output)
    summary["fetched_at"] = datetime.now(UTC).isoformat()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
