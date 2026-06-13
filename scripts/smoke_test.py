# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from scripts.ingest_corpus import run_ingest
from scripts.rebuild_indexes import rebuild_indexes

DEFAULT_CHAT_QUERY = "What is the rollout window for Auth Service v2?"
DEFAULT_CHAT_ANSWER_SNIPPET = "Tuesday 22:00 to 23:00"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Q1 local/API smoke check.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Ingest sample data and rebuild indexes.",
    )
    parser.add_argument(
        "--require-vector",
        action="store_true",
        help="Fail if Qdrant vector indexing is unavailable.",
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip the /health probe; useful for data-only preparation.",
    )
    parser.add_argument("--chat", action="store_true", help="Call /chat after /health.")
    parser.add_argument(
        "--embedding-provider",
        default="mock",
        choices=["mock", "sentence_transformer"],
    )
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--input", type=Path, default=Path("data/sample_corpus"))
    parser.add_argument("--output", type=Path, default=Path("data/generated"))
    parser.add_argument("--chunks", type=Path, default=Path("data/generated/chunks.jsonl"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.qdrant_url:
        os.environ["QDRANT_URL"] = args.qdrant_url
    os.environ["EMBEDDING_PROVIDER"] = args.embedding_provider
    get_settings.cache_clear()

    summary: dict[str, Any] = {}
    if args.prepare:
        summary["prepare"] = _prepare_indexes(args)

    if not args.skip_health:
        health_payload = _wait_for_health(args.base_url, timeout_seconds=args.timeout)
        summary["health"] = health_payload

    if args.chat:
        summary["chat"] = _check_chat(args.base_url)

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def _prepare_indexes(args: argparse.Namespace) -> dict[str, Any]:
    ingest_result = run_ingest(
        input_dir=args.input,
        output_dir=args.output,
        eval_path=_default_eval_path(args.input),
    )
    index_result = _rebuild_with_retries(args)
    return {
        "ingest": ingest_result,
        "index": index_result,
    }


def _default_eval_path(input_dir: Path) -> Path | None:
    if input_dir.as_posix().rstrip("/") == Path("data/sample_corpus").as_posix():
        return Path("data/gold_eval/demo_eval.jsonl")
    return None


def _rebuild_with_retries(args: argparse.Namespace) -> dict[str, Any]:
    deadline = time.monotonic() + args.timeout
    last_result: dict[str, Any] | None = None
    while True:
        last_result = rebuild_indexes(
            chunks_path=args.chunks,
            embedding_provider=args.embedding_provider,
        )
        if last_result.get("vector_index_built") or not args.require_vector:
            return last_result
        if time.monotonic() >= deadline:
            raise SystemExit(
                "Qdrant vector index was not built before timeout. "
                f"Last index result: {json.dumps(last_result, ensure_ascii=False)}"
            )
        time.sleep(2.0)


def _wait_for_health(base_url: str, *, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    health_url = f"{base_url.rstrip('/')}/health"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(health_url, timeout=5.0)
            if response.status_code == 200:
                payload = response.json()
                if payload.get("status") != "ok":
                    raise SystemExit(f"Unexpected health payload: {payload}")
                return payload
            last_error = f"status={response.status_code} body={response.text[:200]}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(1.0)
    raise SystemExit(f"Health check failed for {health_url}: {last_error}")


def _check_chat(base_url: str) -> dict[str, Any]:
    chat_url = f"{base_url.rstrip('/')}/chat"
    response = httpx.post(
        chat_url,
        json={
            "query": DEFAULT_CHAT_QUERY,
            "user_role": "employee",
            "user_department": "Engineering",
            "user_clearance": "internal",
            "retrieval_options": {
                "top_k": 8,
                "top_n_rerank": 4,
                "return_retrieved_chunks": True,
            },
        },
        timeout=20.0,
    )
    if response.status_code != 200:
        raise SystemExit(
            "Chat smoke failed: "
            f"status={response.status_code} body={response.text[:500]}"
        )

    payload = response.json()
    if not payload.get("trace_id"):
        raise SystemExit("Chat smoke failed: response did not include trace_id.")
    if payload.get("response_mode") != "answer":
        raise SystemExit(
            "Chat smoke failed: expected response_mode=answer, got "
            f"{payload.get('response_mode')} with warnings={payload.get('warnings')}"
        )
    if DEFAULT_CHAT_ANSWER_SNIPPET not in payload.get("answer", ""):
        raise SystemExit(f"Chat smoke failed: unexpected answer text: {payload.get('answer')}")

    provider_metadata = payload.get("provider_metadata", {})
    if provider_metadata.get("llm_provider") != "mock":
        raise SystemExit(
            "Smoke test is expected to run with LLM_PROVIDER=mock; got "
            f"{provider_metadata.get('llm_provider')}"
        )

    return {
        "response_mode": payload["response_mode"],
        "trace_id": payload["trace_id"],
        "citation_count": len(payload.get("citations", [])),
        "retrieved_preview_count": len(payload.get("retrieved_chunks_preview", [])),
        "llm_provider": provider_metadata.get("llm_provider"),
        "reranker_provider": provider_metadata.get("reranker_provider"),
        "embedding_provider": provider_metadata.get("embedding_provider"),
        "mock_only": provider_metadata.get("mock_llm_for_local_demo_only") is True,
    }


if __name__ == "__main__":
    main()
