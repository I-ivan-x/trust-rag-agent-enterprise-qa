from __future__ import annotations

from types import SimpleNamespace

import app.eval.real_pipeline as real_pipeline
from app.answer.answer_generator import GeneratedAnswer, GeneratedClaim
from app.core.enums import DecisionReason, ExpectedBehavior
from app.llm.llm_client import BaseLLMClient
from app.schemas.eval import EvalCase
from tests.helpers import make_retrieved_chunk


class _FakeLLM(BaseLLMClient):
    provider = "fake"

    def generate(self, prompt: str) -> str:
        del prompt
        return "{}"


def _case(expected_behavior: str = "answer") -> EvalCase:
    return EvalCase(
        case_id="case-1",
        split="external",
        query="How do I configure CORS?",
        query_type="fact_lookup",
        corpus_source="public_external",
        expected_behavior=expected_behavior,
        gold_doc_ids=["doc-cors"],
        gold_chunk_ids=["chunk-cors"],
        reference_claims=["Use CORSMiddleware."],
    )


def test_real_final_pipeline_preserves_bound_claims(monkeypatch) -> None:
    retrieved = make_retrieved_chunk(
        "chunk-cors",
        "Use CORSMiddleware to configure CORS.",
        doc_id="doc-cors",
    )

    monkeypatch.setattr(real_pipeline, "_get_eval_hybrid_retriever", lambda: object())
    monkeypatch.setattr(real_pipeline, "_get_eval_reranker", lambda: (object(), False))
    monkeypatch.setattr(
        real_pipeline,
        "_trust_pass",
        lambda case, query, retriever, reranker: SimpleNamespace(
            query=query,
            reranked_chunks=[retrieved],
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        real_pipeline,
        "_refusal_for_pass",
        lambda final_pass, warnings: SimpleNamespace(
            should_answer=True,
            selected_chunks=[retrieved],
            response_mode=ExpectedBehavior.answer,
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        real_pipeline,
        "generate_answer",
        lambda query, context_pack, llm_client: GeneratedAnswer(
            answer_text="Use CORSMiddleware.",
            claims=[
                GeneratedClaim(
                    claim_id="claim-0001",
                    text="Use CORSMiddleware.",
                    supporting_chunk_ids=["chunk-cors"],
                )
            ],
        ),
    )

    result = real_pipeline.run_real_final_pipeline(
        _case(),
        "final_gated",
        llm_client=_FakeLLM(),
    )

    assert result.claims
    assert result.claims[0].text == "Use CORSMiddleware."
    assert result.claims[0].supporting_chunk_ids == ["chunk-cors"]
    assert result.claims[0].citation_ids == ["CIT-0001"]
    assert result.citations[0].chunk_id == "chunk-cors"


def test_real_final_pipeline_refusal_has_no_claims(monkeypatch) -> None:
    retrieved = make_retrieved_chunk("chunk-cors", "Use CORSMiddleware.")

    monkeypatch.setattr(real_pipeline, "_get_eval_hybrid_retriever", lambda: object())
    monkeypatch.setattr(real_pipeline, "_get_eval_reranker", lambda: (object(), False))
    monkeypatch.setattr(
        real_pipeline,
        "_trust_pass",
        lambda case, query, retriever, reranker: SimpleNamespace(
            query=query,
            reranked_chunks=[retrieved],
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        real_pipeline,
        "_refusal_for_pass",
        lambda final_pass, warnings: SimpleNamespace(
            should_answer=False,
            selected_chunks=[],
            response_mode=ExpectedBehavior.refuse_no_evidence,
            warnings=["no_evidence"],
        ),
    )

    result = real_pipeline.run_real_final_pipeline(
        _case("refuse_no_evidence"),
        "final_gated",
        llm_client=_FakeLLM(),
    )

    assert result.refused is True
    assert result.decision_reason == DecisionReason.no_evidence
    assert result.claims == []
    assert result.citations == []


def test_direct_llm_baseline_has_no_claims() -> None:
    class DirectLLM(BaseLLMClient):
        provider = "fake"

        def generate(self, prompt: str) -> str:
            del prompt
            return '{"answer_text": "A parametric answer."}'

    result = real_pipeline.run_direct_llm_baseline(
        _case(),
        llm_client=DirectLLM(),
    )

    assert result.refused is False
    assert result.claims == []
    assert result.citations == []
