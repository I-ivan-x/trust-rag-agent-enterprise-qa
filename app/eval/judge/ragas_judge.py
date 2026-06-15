from __future__ import annotations

import json
from typing import Any

from app.eval.judge.base import BaseJudge, BaseLLM, JudgeVerdict, format_cited_chunks


class RagasFaithfulnessJudge(BaseJudge):
    candidate_id = "ragas"
    candidate_name = "J-A RAGAS faithfulness adapter"

    def __init__(self, llm_client: BaseLLM) -> None:
        self.llm_client = llm_client

    def judge(self, claim_text: str, cited_texts: list[str]) -> JudgeVerdict:
        raw = self.llm_client.generate(self.build_prompt(claim_text, cited_texts))
        return _parse_binary_verdict(raw, framework_name="ragas")

    def build_prompt(self, claim_text: str, cited_texts: list[str]) -> str:
        return f"""You are applying a RAGAS-style faithfulness check to one claim.
Treat the CLAIM as the answer statement and the CITED CHUNKS as the contexts.
Do not decompose the answer; judge only this one statement against the contexts.

Return faithful=true only if the claim is fully supported by the cited chunks.
If support is partial, missing, contradictory, or uncertain, return faithful=false.

CLAIM:
{claim_text}

CITED CHUNKS:
{format_cited_chunks(cited_texts)}

Respond with JSON only:
{{"faithful": true|false, "rationale": "<= 2 sentences"}}
"""


def _parse_binary_verdict(raw: str, *, framework_name: str) -> JudgeVerdict:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return JudgeVerdict(
            label="unsupported",
            rationale=f"{framework_name} adapter output was not JSON; fallback applied.",
            warnings=[f"{framework_name}_parse_failed"],
            raw_response=raw,
        )
    if not isinstance(payload, dict):
        return JudgeVerdict(
            label="unsupported",
            rationale=f"{framework_name} adapter output was not an object; fallback applied.",
            warnings=[f"{framework_name}_parse_failed"],
            raw_response=raw,
        )
    faithful = bool(payload.get("faithful", payload.get("supported", False)))
    return JudgeVerdict(
        label="supported" if faithful else "unsupported",
        wrong_side=bool(payload.get("wrong_side_citation", False)),
        rationale=str(payload.get("rationale", "")),
        raw_response=raw,
    )
