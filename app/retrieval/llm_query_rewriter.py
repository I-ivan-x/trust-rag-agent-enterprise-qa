from __future__ import annotations

import json
from collections.abc import Sequence

from app.core.config import get_settings
from app.llm.llm_client import BaseLLMClient, get_llm_client
from app.retrieval.query_rewriter import RewriteDecision
from app.schemas.retrieval import RetrievedChunk

# Hard red line: the rewrite prompt may only ever contain the original query,
# optional retrieved chunk previews, and allowed domain hints. It must never
# include gold_doc_ids, gold_chunk_ids, reference_answer, or expected_rewrite.
_MAX_PREVIEWS = 3
_PREVIEW_CHARS = 240


class LLMQueryRewriter:
    """LLM-backed agentic query rewriter used by final_agentic in real runs."""

    def __init__(
        self,
        client: BaseLLMClient | None = None,
        *,
        model_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.rewrite_llm_model_name
        self.client = client or get_llm_client(
            settings.rewrite_llm_provider,
            model_name=self.model_name,
            purpose="rewrite",
        )

    def rewrite(
        self,
        query: str,
        *,
        chunk_previews: Sequence[RetrievedChunk] | None = None,
        domain_hints: Sequence[str] | None = None,
    ) -> RewriteDecision:
        normalized = query.strip()
        if not normalized:
            return RewriteDecision(
                should_rewrite=False,
                reason="blank_query",
                warnings=["Blank query cannot be rewritten."],
                source="llm",
                model_name=self.model_name,
            )

        prompt = build_rewrite_prompt(
            normalized,
            chunk_previews=chunk_previews,
            domain_hints=domain_hints,
        )
        try:
            raw = self.client.generate(prompt)
        except Exception as exc:  # noqa: BLE001 - record, never fallback to gold data
            return RewriteDecision(
                should_rewrite=False,
                reason="llm_rewrite_failed",
                warnings=[f"llm_rewrite_error:{type(exc).__name__}"],
                source="llm",
                model_name=self.model_name,
            )

        decision = _parse_rewrite_output(raw, original=normalized)
        decision.source = "llm"
        decision.model_name = self.model_name
        return decision


def build_rewrite_prompt(
    query: str,
    *,
    chunk_previews: Sequence[RetrievedChunk] | None = None,
    domain_hints: Sequence[str] | None = None,
) -> str:
    lines = [
        "You rewrite enterprise document search queries to improve retrieval.",
        "Use only the information below. Do not invent document ids or answers.",
        "Return JSON only with fields: should_rewrite (bool), rewritten_query "
        "(string), reason (string).",
        "If the original query is already good, set should_rewrite=false and echo "
        "the original query.",
        f"ORIGINAL_QUERY: {query}",
    ]
    if domain_hints:
        hint_text = ", ".join(str(hint) for hint in domain_hints if str(hint).strip())
        if hint_text:
            lines.append(f"ALLOWED_DOMAIN_HINTS: {hint_text}")
    if chunk_previews:
        lines.append("RETRIEVED_CHUNK_PREVIEWS:")
        for index, item in enumerate(list(chunk_previews)[:_MAX_PREVIEWS], start=1):
            preview = " ".join(item.chunk.text.split())[:_PREVIEW_CHARS]
            lines.append(f"  [{index}] {preview}")
    return "\n".join(lines)


def _parse_rewrite_output(raw: str, *, original: str) -> RewriteDecision:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return RewriteDecision(
            should_rewrite=False,
            reason="llm_rewrite_non_json",
            warnings=["llm_rewrite_output_not_json"],
        )
    if not isinstance(payload, dict):
        return RewriteDecision(
            should_rewrite=False,
            reason="llm_rewrite_non_object",
            warnings=["llm_rewrite_output_not_object"],
        )

    rewritten = str(payload.get("rewritten_query") or "").strip()
    reason = str(payload.get("reason") or "llm_rewrite").strip()
    wants_rewrite = bool(payload.get("should_rewrite"))

    if not wants_rewrite or not rewritten or rewritten == original:
        return RewriteDecision(
            should_rewrite=False,
            rewritten_query=None,
            reason=reason or "llm_no_rewrite",
        )
    return RewriteDecision(
        should_rewrite=True,
        rewritten_query=rewritten,
        reason=reason or "llm_rewrite",
    )


def get_query_rewriter(provider: str | None = None) -> LLMQueryRewriter | None:
    """Return an LLM rewriter when a real rewrite provider is configured, else None.

    None signals callers to fall back to the rule-based rewriter.
    """
    settings = get_settings()
    selected = (provider or settings.rewrite_llm_provider).lower().replace("-", "_")
    if selected in {"mock", "rule_based", "none", ""}:
        return None
    return LLMQueryRewriter()
