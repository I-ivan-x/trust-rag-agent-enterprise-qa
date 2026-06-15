from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator

JudgeLabel = Literal["supported", "weak", "unsupported"]


class JudgeVerdict(BaseModel):
    label: JudgeLabel
    wrong_side: bool = False
    rationale: str = ""
    warnings: list[str] = Field(default_factory=list)
    raw_response: str | None = None
    judge_based: bool = True

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value):
        normalized = str(value or "").strip().lower()
        if normalized in {"support", "supported", "faithful", "true", "yes"}:
            return "supported"
        if normalized in {"weak", "partial", "partially_supported"}:
            return "weak"
        return "unsupported"


class BaseLLM(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class BaseJudge:
    candidate_id = "base"
    candidate_name = "Base judge"

    def judge(self, claim_text: str, cited_texts: list[str]) -> JudgeVerdict:
        raise NotImplementedError

    def build_prompt(self, claim_text: str, cited_texts: list[str]) -> str:
        raise NotImplementedError


def format_cited_chunks(cited_texts: list[str]) -> str:
    if not cited_texts:
        return "[no cited chunks provided]"
    return "\n\n".join(
        f"[chunk {index}]\n{text.strip()}" for index, text in enumerate(cited_texts, start=1)
    )
