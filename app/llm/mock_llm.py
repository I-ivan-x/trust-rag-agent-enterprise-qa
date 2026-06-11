from __future__ import annotations

import json
import re
import warnings

MOCK_LLM_WARNING = (
    "MockLLMClient is deterministic and for tests/local demo/smoke only; "
    "do not use it for formal end-to-end metrics."
)

_CONTEXT_BLOCK_PATTERN = re.compile(
    r"^CHUNK_ID:\s*(?P<chunk_id>[^\n]+)\n"
    r"DOC_ID:\s*(?P<doc_id>[^\n]+)\n"
    r"SECTION:\s*(?P<section>[^\n]*)\n"
    r"TEXT:\s*(?P<text>.*?)(?=\n---CONTEXT_CHUNK---|\nEND_CONTEXT)",
    re.MULTILINE | re.DOTALL,
)


class MockLLMClient:
    """Deterministic local demo/smoke LLM; never use for formal E2E metrics."""

    def __init__(self) -> None:
        warnings.warn(MOCK_LLM_WARNING, RuntimeWarning, stacklevel=2)

    def generate(self, prompt: str) -> str:
        chunks = [
            {
                "chunk_id": match.group("chunk_id").strip(),
                "doc_id": match.group("doc_id").strip(),
                "section": match.group("section").strip(),
                "text": match.group("text").strip(),
            }
            for match in _CONTEXT_BLOCK_PATTERN.finditer(prompt)
        ]
        if not chunks:
            return json.dumps(
                {
                    "answer_text": (
                        "I do not have enough provided context to answer this question."
                    ),
                    "claims": [],
                    "response_mode": "refuse_no_evidence",
                    "warnings": [MOCK_LLM_WARNING, "no_context"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )

        best = chunks[0]
        answer_text = _answer_from_context(best["text"])
        return json.dumps(
            {
                "answer_text": answer_text,
                "claims": [
                    {
                        "claim_id": "claim-0001",
                        "text": answer_text,
                        "supporting_chunk_ids": [best["chunk_id"]],
                    }
                ],
                "response_mode": "answer",
                "warnings": [MOCK_LLM_WARNING],
            },
            ensure_ascii=False,
            sort_keys=True,
        )


def _answer_from_context(text: str) -> str:
    normalized = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    for sentence in sentences:
        lowered = sentence.lower()
        if "refresh token" in lowered and "rate" in lowered:
            return sentence
    return sentences[0] if sentences and sentences[0] else normalized
