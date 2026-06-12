from __future__ import annotations

from app.core.enums import ExpectedBehavior, QueryType
from app.retrieval.llm_query_rewriter import LLMQueryRewriter
from app.schemas.eval import EvalCase


class _CaptureLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return '{"should_rewrite": false, "rewritten_query": "", "reason": "noop"}'


def _case() -> EvalCase:
    return EvalCase(
        case_id="case-leak-check",
        query="What is the token ttl?",
        query_type=QueryType.single_doc_fact,
        expected_behavior=ExpectedBehavior.answer,
        expected_rewrite="LEAK_EXPECTED_REWRITE",
        gold_doc_ids=["LEAK_GOLD_DOC"],
        gold_chunk_ids=["LEAK_GOLD_CHUNK"],
        reference_answer="LEAK_REFERENCE_ANSWER",
        reference_claims=["LEAK_REFERENCE_CLAIM"],
    )


def test_llm_rewrite_prompt_never_contains_gold_or_reference() -> None:
    case = _case()
    capture = _CaptureLLM()
    LLMQueryRewriter(client=capture).rewrite(case.query, chunk_previews=[])

    assert capture.prompts, "rewrite must invoke the LLM"
    prompt = capture.prompts[0]
    for forbidden in (
        "LEAK_EXPECTED_REWRITE",
        "LEAK_GOLD_DOC",
        "LEAK_GOLD_CHUNK",
        "LEAK_REFERENCE_ANSWER",
        "LEAK_REFERENCE_CLAIM",
    ):
        assert forbidden not in prompt
    assert case.query in prompt


def test_real_trace_marks_expected_rewrite_present_but_unused() -> None:
    from app.eval.runner import _trace_row

    case = _case()
    trace = _trace_row(
        trace_id="t-1",
        case=case,
        system_name="final_agentic",
        retrieval_query=case.query,
        actual_rewritten_query=None,
        rewrite_source="llm",
        rewrite_model_name="deepseek-v4-flash",
        retrieved=[],
        events=[],
    )
    assert trace["expected_rewrite_present"] is True
    assert trace["expected_rewrite_policy"] == "informational_only"
    # The retrieval query must be the original query, never the expected_rewrite value.
    assert trace["retrieval_query"] == case.query
    assert trace["retrieval_query"] != case.expected_rewrite
