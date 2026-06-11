from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.context.context_assembler import ContextPack
from app.core.enums import ExpectedBehavior
from app.llm.llm_client import BaseLLMClient


class GeneratedClaim(BaseModel):
    claim_id: str
    text: str
    supporting_chunk_ids: list[str] = Field(default_factory=list)


class GeneratedAnswer(BaseModel):
    answer_text: str
    claims: list[GeneratedClaim] = Field(default_factory=list)
    raw_model_output: str | None = None
    warnings: list[str] = Field(default_factory=list)
    response_mode: ExpectedBehavior = ExpectedBehavior.answer


def generate_answer(
    query: str,
    context_pack: ContextPack,
    llm_client: BaseLLMClient,
) -> GeneratedAnswer:
    if not context_pack.chunks:
        return GeneratedAnswer(
            answer_text="I do not have enough provided context to answer this question.",
            claims=[],
            raw_model_output=None,
            warnings=[*context_pack.warnings, "no_context"],
            response_mode=ExpectedBehavior.refuse_no_evidence,
        )

    prompt = build_prompt(query, context_pack)
    raw_output = llm_client.generate(prompt)
    valid_chunk_ids = {chunk.chunk_id for chunk in context_pack.chunks}
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        return _fallback_answer(
            context_pack=context_pack,
            raw_output=raw_output,
            warnings=["model_output_json_parse_failed"],
        )

    answer_text = str(payload.get("answer_text") or "").strip()
    if not answer_text:
        return _fallback_answer(
            context_pack=context_pack,
            raw_output=raw_output,
            warnings=["model_output_missing_answer_text"],
        )

    warnings = list(context_pack.warnings)
    warnings.extend(_string_list(payload.get("warnings", [])))
    claims: list[GeneratedClaim] = []
    for index, item in enumerate(payload.get("claims") or [], start=1):
        if not isinstance(item, dict):
            warnings.append(f"claim_{index}_not_object")
            continue
        claim_text = str(item.get("text") or "").strip()
        if not claim_text:
            warnings.append(f"claim_{index}_missing_text")
            continue
        requested_ids = _string_list(item.get("supporting_chunk_ids", []))
        valid_ids = [chunk_id for chunk_id in requested_ids if chunk_id in valid_chunk_ids]
        invalid_ids = [chunk_id for chunk_id in requested_ids if chunk_id not in valid_chunk_ids]
        if invalid_ids:
            warnings.append(
                f"claim_{index}_ignored_out_of_context_chunk_ids={','.join(invalid_ids)}"
            )
        claims.append(
            GeneratedClaim(
                claim_id=str(item.get("claim_id") or f"claim-{index:04d}"),
                text=claim_text,
                supporting_chunk_ids=valid_ids,
            )
        )

    if not claims:
        claims = [
            GeneratedClaim(
                claim_id="claim-0001",
                text=answer_text,
                supporting_chunk_ids=[context_pack.chunks[0].chunk_id],
            )
        ]
        warnings.append("model_output_missing_claims")

    response_mode = _parse_response_mode(
        payload.get("response_mode"),
        default=ExpectedBehavior.answer,
    )
    return GeneratedAnswer(
        answer_text=answer_text,
        claims=claims,
        raw_model_output=raw_output,
        warnings=warnings,
        response_mode=response_mode,
    )


def build_prompt(query: str, context_pack: ContextPack) -> str:
    context_blocks = []
    for chunk in context_pack.chunks:
        section = " > ".join(chunk.section_path)
        context_blocks.append(
            "\n".join(
                [
                    "---CONTEXT_CHUNK---",
                    f"CHUNK_ID: {chunk.chunk_id}",
                    f"DOC_ID: {chunk.doc_id}",
                    f"SECTION: {section}",
                    f"TEXT: {chunk.text}",
                ]
            )
        )
    return "\n".join(
        [
            "You are TrustRAG Enterprise QA.",
            "Answer only from the provided context. Do not use outside knowledge.",
            "Return JSON only with fields: answer_text, claims, response_mode, warnings.",
            "Each claim must include claim_id, text, and supporting_chunk_ids.",
            "supporting_chunk_ids must be copied exactly from the provided context.",
            f"QUESTION: {query}",
            "BEGIN_CONTEXT",
            *context_blocks,
            "END_CONTEXT",
        ]
    )


def _fallback_answer(
    context_pack: ContextPack,
    raw_output: str,
    warnings: list[str],
) -> GeneratedAnswer:
    first_chunk = context_pack.chunks[0]
    sentence = _first_sentence(first_chunk.text)
    return GeneratedAnswer(
        answer_text=sentence,
        claims=[
            GeneratedClaim(
                claim_id="claim-0001",
                text=sentence,
                supporting_chunk_ids=[first_chunk.chunk_id],
            )
        ],
        raw_model_output=raw_output,
        warnings=[*context_pack.warnings, *warnings],
        response_mode=ExpectedBehavior.answer,
    )


def _first_sentence(text: str) -> str:
    normalized = " ".join(text.split())
    for marker in (". ", "? ", "! "):
        if marker in normalized:
            return normalized.split(marker, maxsplit=1)[0] + marker.strip()
    return normalized


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item) for item in value if str(item).strip()]


def _parse_response_mode(value: Any, default: ExpectedBehavior) -> ExpectedBehavior:
    if not value:
        return default
    try:
        return ExpectedBehavior(str(value))
    except ValueError:
        return default
