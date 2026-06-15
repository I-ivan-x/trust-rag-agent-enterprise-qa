from __future__ import annotations

import json
from typing import Any

from app.eval.judge.base import BaseJudge, BaseLLM, JudgeVerdict, format_cited_chunks


class DeepEvalFaithfulnessJudge(BaseJudge):
    candidate_id = "deepeval"
    candidate_name = "J-B DeepEval faithfulness/G-Eval adapter"

    def __init__(self, llm_client: BaseLLM) -> None:
        self.llm_client = llm_client

    def judge(self, claim_text: str, cited_texts: list[str]) -> JudgeVerdict:
        raw = self.llm_client.generate(self.build_prompt(claim_text, cited_texts))
        return _parse_binary_verdict(raw)

    def build_prompt(self, claim_text: str, cited_texts: list[str]) -> str:
        return f"""You are applying a DeepEval-style faithfulness metric to one claim.
Use this rubric:
- pass=true only when the claim is fully attributable to the cited chunks.
- pass=false when the citation is missing, partial, contradictory, or only loosely related.

Evaluate exactly one claim. Do not use external knowledge.

CLAIM:
{claim_text}

CITED CHUNKS:
{format_cited_chunks(cited_texts)}

Respond with JSON only:
{{"pass": true|false, "rationale": "<= 2 sentences"}}
"""


def _parse_binary_verdict(raw: str) -> JudgeVerdict:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return JudgeVerdict(
            label="unsupported",
            rationale="deepeval adapter output was not JSON; fallback applied.",
            warnings=["deepeval_parse_failed"],
            raw_response=raw,
        )
    if not isinstance(payload, dict):
        return JudgeVerdict(
            label="unsupported",
            rationale="deepeval adapter output was not an object; fallback applied.",
            warnings=["deepeval_parse_failed"],
            raw_response=raw,
        )
    passed = bool(payload.get("pass", payload.get("faithful", False)))
    return JudgeVerdict(
        label="supported" if passed else "unsupported",
        wrong_side=bool(payload.get("wrong_side_citation", False)),
        rationale=str(payload.get("rationale", "")),
        raw_response=raw,
    )
