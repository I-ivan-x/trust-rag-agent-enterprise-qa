from __future__ import annotations

import json
from typing import Any

from app.eval.judge.base import BaseJudge, BaseLLM, JudgeVerdict, format_cited_chunks


class CustomCitationJudge(BaseJudge):
    candidate_id = "custom"
    candidate_name = "J-C custom citation-support judge"

    def __init__(self, llm_client: BaseLLM) -> None:
        self.llm_client = llm_client

    def judge(self, claim_text: str, cited_texts: list[str]) -> JudgeVerdict:
        prompt = self.build_prompt(claim_text, cited_texts)
        raw = self.llm_client.generate(prompt)
        return parse_custom_verdict(raw)

    def build_prompt(self, claim_text: str, cited_texts: list[str]) -> str:
        cited_chunks_text = format_cited_chunks(cited_texts)
        return f"""You are auditing whether cited evidence supports a claim from a
question-answering system. You will see one CLAIM and the full text of its
CITED CHUNKS. Judge only from the cited text. You have no other knowledge:
if the cited text does not contain it, it does not exist.

Rules:
1. supported - every factual element of the claim (entities, numbers,
   conditions) is verifiable from the cited text alone. Paraphrase is fine.
   Numeric values must match exactly.
2. weak - the cited text covers part of the claim, or supporting it requires
   an inference step beyond paraphrase.
3. unsupported - the cited text does not contain the claim's content, or
   contradicts it.
4. If multiple chunks are cited, judge against their union.
5. When torn between two labels, choose the lower one.
6. wrong_side_citation = true if the cited text discusses a confusably similar
   topic, version, or document that is plausibly NOT what the claim is actually
   about.

CLAIM:
{claim_text}

CITED CHUNKS:
{cited_chunks_text}

Respond with JSON only:
{{"label": "supported|weak|unsupported",
 "wrong_side_citation": true|false,
 "rationale": "<= 2 sentences, quoting the decisive span or its absence"}}
"""


def parse_custom_verdict(raw: str) -> JudgeVerdict:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return JudgeVerdict(
            label="unsupported",
            wrong_side=False,
            rationale="Judge output was not valid JSON; conservative fallback applied.",
            warnings=["judge_parse_failed"],
            raw_response=raw,
        )
    if not isinstance(payload, dict):
        return JudgeVerdict(
            label="unsupported",
            wrong_side=False,
            rationale="Judge output was not a JSON object; conservative fallback applied.",
            warnings=["judge_parse_failed"],
            raw_response=raw,
        )
    warnings: list[str] = []
    wrong_side = payload.get("wrong_side_citation", payload.get("wrong_side", False))
    try:
        return JudgeVerdict(
            label=payload.get("label", "unsupported"),
            wrong_side=bool(wrong_side),
            rationale=str(payload.get("rationale", "")),
            warnings=warnings,
            raw_response=raw,
        )
    except ValueError:
        return JudgeVerdict(
            label="unsupported",
            wrong_side=bool(wrong_side),
            rationale=str(payload.get("rationale", "Invalid label; fallback applied.")),
            warnings=["judge_invalid_label"],
            raw_response=raw,
        )
