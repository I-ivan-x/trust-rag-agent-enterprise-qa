from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.ingest.metadata_extractor import extract_front_matter

SUPPORTED_PAIR_TYPES = {"adjacent_topic", "similar_title"}
_TITLE_STOPWORDS = {
    "a",
    "and",
    "as",
    "for",
    "in",
    "of",
    "the",
    "to",
    "with",
}


def build_hard_negative_corpus(
    public_corpus_dir: Path = Path("data/public_corpus"),
    output_dir: Path = Path("data/hard_negative_corpus"),
    pair_count: int = 20,
) -> dict[str, Any]:
    source_docs = _load_public_docs(public_corpus_dir)
    if len(source_docs) < 2:
        raise ValueError(
            f"Need at least two public documents to build hard negatives: {public_corpus_dir}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_records = []
    for index in range(pair_count):
        doc_a = source_docs[(index * 2) % len(source_docs)]
        doc_b = source_docs[(index * 2 + 1) % len(source_docs)]
        group_id = f"hn-fastapi-{index + 1:04d}"
        pair_type = _pair_type(doc_a, doc_b)
        path_a = output_dir / group_id / f"a-{Path(doc_a['path']).name}"
        path_b = output_dir / group_id / f"b-{Path(doc_b['path']).name}"
        _write_hard_negative_doc(path_a, doc_a, group_id, side="a")
        _write_hard_negative_doc(path_b, doc_b, group_id, side="b")
        manifest_records.append(
            {
                "hard_negative_group_id": group_id,
                "pair_type": pair_type,
                "doc_id_a": f"hard-negative-{group_id}-a",
                "doc_id_b": f"hard-negative-{group_id}-b",
                "source_path_a": path_a.as_posix(),
                "source_path_b": path_b.as_posix(),
                "why_hard": _why_hard(pair_type, doc_a, doc_b),
                "expected_confusion": _expected_confusion(pair_type, doc_a, doc_b),
                "source_origin": "public_repo",
            }
        )

    manifest_path = output_dir / "hard_negative_manifest.jsonl"
    _write_jsonl(manifest_path, manifest_records)
    return {
        "pair_count": len(manifest_records),
        "hard_negative_manifest_path": manifest_path.as_posix(),
        "output_dir": output_dir.as_posix(),
    }


def _load_public_docs(public_corpus_dir: Path) -> list[dict[str, Any]]:
    docs = []
    for path in sorted(public_corpus_dir.rglob("*.md"), key=lambda item: item.as_posix()):
        if "/overlay/" in path.as_posix() or path.name.startswith("."):
            continue
        front_matter, body = extract_front_matter(path.read_text(encoding="utf-8"))
        if not body.strip():
            continue
        title = str(front_matter.get("title") or Path(path).stem)
        docs.append(
            {
                "path": path.as_posix(),
                "front_matter": front_matter,
                "body": body,
                "title": title,
                "title_terms": _title_terms(title),
                "relative_parent": path.parent.name,
            }
        )
    return docs


def _write_hard_negative_doc(
    path: Path,
    source_doc: dict[str, Any],
    group_id: str,
    side: str,
) -> None:
    front_matter = dict(source_doc["front_matter"])
    title = str(front_matter.get("title") or Path(source_doc["path"]).stem)
    source_url = front_matter.get("source_url")
    payload = {
        **front_matter,
        "doc_id": f"hard-negative-{group_id}-{side}",
        "title": f"Hard Negative {group_id.upper()} {side.upper()}: {title}",
        "doc_type": front_matter.get("doc_type") or "public_doc",
        "status": front_matter.get("status") or "active",
        "version": front_matter.get("version") or "v1",
        "access_level": front_matter.get("access_level") or "internal",
        "allowed_roles": front_matter.get("allowed_roles") or ["employee", "engineer"],
        "language": "en",
        "source_path": path.as_posix(),
        "corpus_source": "hard_negative",
        "source_origin": front_matter.get("source_origin") or "public_repo",
        "source_license_note": front_matter.get("source_license_note")
        or "Derived from public FastAPI documentation under the upstream project license.",
        "source_url": source_url,
        "hard_negative_group_id": group_id,
        "metadata_origin": "native",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + source_doc["body"].strip()
        + "\n",
        encoding="utf-8",
    )


def _pair_type(doc_a: dict[str, Any], doc_b: dict[str, Any]) -> str:
    shared_terms = _shared_title_terms(doc_a, doc_b)
    if shared_terms:
        return "similar_title"
    return "adjacent_topic"


def _why_hard(pair_type: str, doc_a: dict[str, Any], doc_b: dict[str, Any]) -> str:
    title_a = _title(doc_a)
    title_b = _title(doc_b)
    if pair_type == "similar_title":
        shared = ", ".join(sorted(_shared_title_terms(doc_a, doc_b)))
        return (
            f"similar_title: '{title_a}' and '{title_b}' share title terms "
            f"({shared}) but point to different FastAPI documentation pages."
        )
    return (
        f"adjacent_topic: '{title_a}' and '{title_b}' are adjacent FastAPI docs "
        f"neighbors from {doc_a['relative_parent']} / {doc_b['relative_parent']}."
    )


def _expected_confusion(pair_type: str, doc_a: dict[str, Any], doc_b: dict[str, Any]) -> str:
    title_a = _title(doc_a)
    title_b = _title(doc_b)
    if pair_type == "similar_title":
        return (
            f"Queries using shared title terms may retrieve '{title_b}' when the "
            f"answer requires details from '{title_a}', or vice versa."
        )
    return (
        f"Broad tutorial queries may confuse adjacent docs '{title_a}' and '{title_b}' "
        "because they appear near each other in the same public documentation subset."
    )


def _title(doc: dict[str, Any]) -> str:
    return str(doc.get("title") or doc["front_matter"].get("title") or Path(doc["path"]).stem)


def _shared_title_terms(doc_a: dict[str, Any], doc_b: dict[str, Any]) -> set[str]:
    return set(doc_a["title_terms"]) & set(doc_b["title_terms"])


def _title_terms(title: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9]+", title.lower())
        if len(term) >= 3 and term not in _TITLE_STOPWORDS
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "doc"
