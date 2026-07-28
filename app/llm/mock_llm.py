from __future__ import annotations

import json
import re
import warnings

MOCK_LLM_WARNING = (
    "MockLLMClient is deterministic and for tests/local demo/smoke only; "
    "do not use it for formal end-to-end metrics."
)

_CONTEXT_MARKER = "---CONTEXT_CHUNK---"
_END_CONTEXT_MARKER = "END_CONTEXT"


class MockLLMClient:
    """Deterministic local demo/smoke LLM; never use for formal E2E metrics."""

    def __init__(self) -> None:
        warnings.warn(MOCK_LLM_WARNING, RuntimeWarning, stacklevel=2)

    def generate(self, prompt: str) -> str:
        chunks = _parse_context_blocks(prompt)
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


def _parse_context_blocks(prompt: str) -> list[dict[str, str]]:
    """Parse the deterministic prompt format in linear time."""
    chunks: list[dict[str, str]] = []
    delimiter = f"\n{_CONTEXT_MARKER}\n"
    for candidate in prompt.split(delimiter)[1:]:
        block = candidate.split(f"\n{_END_CONTEXT_MARKER}", maxsplit=1)[0]
        lines = block.split("\n", maxsplit=3)
        if len(lines) != 4:
            continue
        chunk_line, doc_line, section_line, text_line = lines
        prefixes = ("CHUNK_ID: ", "DOC_ID: ", "SECTION: ", "TEXT: ")
        if not all(line.startswith(prefix) for line, prefix in zip(lines, prefixes, strict=True)):
            continue
        chunks.append(
            {
                "chunk_id": chunk_line.removeprefix(prefixes[0]).strip(),
                "doc_id": doc_line.removeprefix(prefixes[1]).strip(),
                "section": section_line.removeprefix(prefixes[2]).strip(),
                "text": text_line.removeprefix(prefixes[3]).strip(),
            }
        )
    return chunks


def _answer_from_context(text: str) -> str:
    normalized = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    for sentence in sentences:
        lowered = sentence.lower()
        if "refresh token" in lowered and "rate" in lowered:
            return sentence
    return sentences[0] if sentences and sentences[0] else normalized
