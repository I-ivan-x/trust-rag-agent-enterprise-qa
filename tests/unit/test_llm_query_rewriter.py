from __future__ import annotations

from app.retrieval.llm_query_rewriter import LLMQueryRewriter, build_rewrite_prompt


class _CaptureLLM:
    def __init__(self, output: str) -> None:
        self.output = output
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.output


class _BoomLLM:
    def generate(self, prompt: str) -> str:
        raise RuntimeError("network down")


def test_prompt_contains_only_allowed_inputs() -> None:
    prompt = build_rewrite_prompt(
        "token ttl",
        domain_hints=["auth"],
        chunk_previews=[],
    )
    assert "token ttl" in prompt
    assert "auth" in prompt
    assert "expected_rewrite" not in prompt.lower()
    assert "gold_doc" not in prompt.lower()
    assert "reference_answer" not in prompt.lower()


def test_rewrite_parses_json_decision() -> None:
    llm = _CaptureLLM(
        '{"should_rewrite": true, "rewritten_query": "access token lifetime", '
        '"reason": "expand_abbreviation"}'
    )
    decision = LLMQueryRewriter(client=llm).rewrite("token ttl")
    assert decision.should_rewrite is True
    assert decision.rewritten_query == "access token lifetime"
    assert decision.source == "llm"
    assert decision.model_name


def test_rewrite_same_as_original_is_noop() -> None:
    llm = _CaptureLLM(
        '{"should_rewrite": true, "rewritten_query": "token ttl", "reason": "x"}'
    )
    decision = LLMQueryRewriter(client=llm).rewrite("token ttl")
    assert decision.should_rewrite is False


def test_rewrite_failure_records_warning_without_fallback() -> None:
    decision = LLMQueryRewriter(client=_BoomLLM()).rewrite("token ttl")
    assert decision.should_rewrite is False
    assert decision.rewritten_query is None
    assert decision.source == "llm"
    assert any("llm_rewrite_error" in warning for warning in decision.warnings)


def test_rewrite_non_json_is_noop() -> None:
    decision = LLMQueryRewriter(client=_CaptureLLM("not json at all")).rewrite("token ttl")
    assert decision.should_rewrite is False
    assert "llm_rewrite_output_not_json" in decision.warnings
