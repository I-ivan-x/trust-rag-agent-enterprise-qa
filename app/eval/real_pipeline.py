from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.agent.controller import RuleController
from app.agent.llm_controller import LLMController
from app.agent.loop import run_agentic_v2_loop
from app.answer.answer_generator import generate_answer
from app.answer.citation_binder import BoundClaim, bind_citations
from app.answer.refusal_controller import decide_response_mode
from app.context.context_assembler import assemble_context
from app.core.config import get_settings
from app.core.enums import DecisionReason, ExpectedBehavior
from app.guards.evidence_gate import EvidenceGateConfig, evidence_gate_config_from_settings
from app.llm.llm_client import BaseLLMClient, get_llm_client
from app.rerank.reranker import BaseReranker, get_reranker
from app.retrieval.llm_query_rewriter import get_query_rewriter
from app.retrieval.query_rewriter import RewriteDecision
from app.schemas.citation import Citation
from app.schemas.eval import EvalCase
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk
from app.service.chat_service import (
    _acl_denies_required_evidence,
    _deprecated_warning_for_policy,
    _make_hybrid_retriever,
    _normalize_trust_gate_policy,
    _query_targets_deprecated,
)
from app.workflow.orchestrator import run_trust_gated_pass
from app.workflow.state import RetrievalPassResult

_REAL_RUN_OPTIONS = RetrievalOptions(
    top_k_dense=20,
    top_k_sparse=20,
    top_n_rerank=8,
    return_trace=True,
)


@dataclass
class RealFinalResult:
    reranked_chunks: list[RetrievedChunk]
    first_pass_reranked: list[RetrievedChunk] | None
    refused: bool
    decision_reason: DecisionReason
    response_mode: ExpectedBehavior
    citations: list[Citation]
    answer_text: str
    rewrite_source: str
    actual_rewritten_query: str | None
    rewrite_model_name: str | None
    rewrite_reason: str | None
    second_pass_attempted: bool
    reranker_unavailable: bool
    gate_decisions: dict[str, Any] = field(default_factory=dict)
    agent_trace: dict[str, Any] = field(default_factory=dict)
    claims: list[BoundClaim] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_real_llm_answer: bool = False


class _IdentityReranker:
    """Passthrough used only when the real reranker cannot be loaded."""

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        del query
        return chunks if top_n is None else chunks[:top_n]


def _resolve_reranker() -> tuple[BaseReranker, bool]:
    settings = get_settings()
    if settings.reranker_provider.lower() == "mock":
        # A mock reranker must never be presented as a real reranker.
        return _IdentityReranker(), True
    try:
        return get_reranker(settings.reranker_provider), False
    except Exception:
        return _IdentityReranker(), True


@lru_cache(maxsize=1)
def _get_eval_hybrid_retriever():
    return _make_hybrid_retriever()


@lru_cache(maxsize=1)
def _get_eval_reranker() -> tuple[BaseReranker, bool]:
    return _resolve_reranker()


def run_real_final_pipeline(
    case: EvalCase,
    system_name: str,
    *,
    llm_client: BaseLLMClient | None = None,
    max_output_tokens: int | None = None,
    evidence_gate_config: EvidenceGateConfig | None = None,
    trust_gate_policy: str | None = None,
    retriever: Any | None = None,
    reranker: BaseReranker | None = None,
    reranker_unavailable: bool | None = None,
) -> RealFinalResult:
    settings = get_settings()
    resolved_trust_gate_policy = _normalize_trust_gate_policy(
        trust_gate_policy or getattr(settings, "trust_gate_policy", "legacy")
    )
    resolved_retriever = retriever or _get_eval_hybrid_retriever()
    if reranker is None:
        resolved_reranker, resolved_reranker_unavailable = _get_eval_reranker()
    else:
        resolved_reranker = reranker
        resolved_reranker_unavailable = bool(reranker_unavailable)
    rewrite_source = "none"
    actual_rewritten_query: str | None = None
    rewrite_model_name: str | None = None
    rewrite_reason: str | None = None
    second_pass_attempted = False
    first_pass_reranked: list[RetrievedChunk] | None = None
    agent_trace: dict[str, Any] = {}
    warnings: list[str] = []

    if system_name in {
        "final_agentic_v2",
        "final_agentic_v2_rule",
        "final_agentic_v2_llm",
    }:
        controller = None
        if system_name == "final_agentic_v2_llm":
            controller_client = llm_client or get_llm_client(
                settings.llm_provider,
                max_output_tokens=max_output_tokens,
                temperature=0,
                purpose="controller",
            )
            controller = LLMController(
                controller_client,
                fallback=RuleController(),
            )
        loop_result = run_agentic_v2_loop(
            case=case,
            retriever=resolved_retriever,
            reranker=resolved_reranker,
            retrieval_options=_REAL_RUN_OPTIONS,
            evidence_gate_config=evidence_gate_config,
            controller=controller,
        )
        first_pass = loop_result.first_pass
        final_pass = loop_result.final_pass
        first_pass_reranked = (
            first_pass.reranked_chunks if final_pass is not first_pass else None
        )
        actual_rewritten_query = loop_result.actual_rewritten_query
        if actual_rewritten_query:
            rewrite_source = (
                "llm_controller"
                if loop_result.controller_source == "llm"
                else "rule_controller"
            )
        rewrite_reason = loop_result.terminal_reason
        second_pass_attempted = loop_result.second_pass_attempted
        agent_trace = loop_result.trace_fields
    else:
        first_pass = _trust_pass_with_optional_config(
            case,
            case.query,
            resolved_retriever,
            resolved_reranker,
            evidence_gate_config=evidence_gate_config,
        )
        final_pass = first_pass

        if system_name == "final_agentic" and _should_rewrite(
            first_pass,
            trust_gate_policy=resolved_trust_gate_policy,
        ):
            decision = _agentic_rewrite(case, first_pass)
            rewrite_source = decision.source
            rewrite_model_name = decision.model_name
            rewrite_reason = decision.reason
            warnings.extend(decision.warnings)
            if decision.should_rewrite and decision.rewritten_query:
                actual_rewritten_query = decision.rewritten_query
                second_pass_attempted = True
                first_pass_reranked = first_pass.reranked_chunks
                final_pass = _trust_pass_with_optional_config(
                    case,
                    decision.rewritten_query,
                    resolved_retriever,
                    resolved_reranker,
                    evidence_gate_config=evidence_gate_config,
                )

    warnings.extend(first_pass.warnings)
    if final_pass is not first_pass:
        warnings.extend(final_pass.warnings)

    refusal = _refusal_for_pass_with_optional_policy(
        final_pass,
        warnings,
        trust_gate_policy=resolved_trust_gate_policy,
    )

    citations: list[Citation] = []
    claims: list[BoundClaim] = []
    answer_text = ""
    used_real_llm_answer = False
    if refusal.should_answer:
        context_pack = assemble_context(
            final_pass.query,
            refusal.selected_chunks,
            token_budget=settings.max_context_tokens,
            max_chunks=_REAL_RUN_OPTIONS.top_n_rerank,
        )
        answer_client = llm_client or get_llm_client(
            settings.llm_provider,
            max_output_tokens=max_output_tokens,
        )
        generated = generate_answer(final_pass.query, context_pack, answer_client)
        bound = bind_citations(generated, context_pack)
        answer_text = bound.answer_text
        claims = bound.claims
        citations = bound.citations
        warnings.extend(bound.warnings)
        used_real_llm_answer = bool(context_pack.chunks)
    else:
        answer_text = _refusal_text(refusal.response_mode)
        warnings.extend(refusal.warnings)

    return RealFinalResult(
        reranked_chunks=final_pass.reranked_chunks,
        first_pass_reranked=first_pass_reranked,
        refused=not refusal.should_answer,
        decision_reason=_decision_reason(refusal.response_mode),
        response_mode=refusal.response_mode,
        citations=citations,
        answer_text=answer_text,
        rewrite_source=rewrite_source,
        actual_rewritten_query=actual_rewritten_query,
        rewrite_model_name=rewrite_model_name,
        rewrite_reason=rewrite_reason,
        second_pass_attempted=second_pass_attempted,
        reranker_unavailable=resolved_reranker_unavailable,
        gate_decisions=_gate_decisions(final_pass),
        agent_trace=agent_trace,
        claims=claims,
        warnings=warnings,
        used_real_llm_answer=used_real_llm_answer,
    )


def run_direct_llm_baseline(
    case: EvalCase,
    *,
    llm_client: BaseLLMClient | None = None,
    max_output_tokens: int | None = None,
) -> RealFinalResult:
    """Parametric baseline: no retrieved context, no citations, no grounding."""
    settings = get_settings()
    client = llm_client or get_llm_client(
        settings.llm_provider,
        max_output_tokens=max_output_tokens,
    )
    prompt = (
        "Answer the question from your own knowledge. Return JSON only with fields "
        "answer_text (string), claims (empty list), response_mode ('answer'), "
        "warnings (list).\n"
        f"QUESTION: {case.query}"
    )
    warnings = ["direct_llm baseline uses no retrieved context and produces no citations."]
    try:
        raw = client.generate(prompt)
    except Exception as exc:  # noqa: BLE001 - record as system error, never fallback
        return RealFinalResult(
            reranked_chunks=[],
            first_pass_reranked=None,
            refused=True,
            decision_reason=DecisionReason.system_error,
            response_mode=ExpectedBehavior.system_error,
            citations=[],
            answer_text="",
            rewrite_source="none",
            actual_rewritten_query=None,
            rewrite_model_name=None,
            rewrite_reason=None,
            second_pass_attempted=False,
            reranker_unavailable=False,
            gate_decisions={},
            agent_trace={},
            claims=[],
            warnings=[*warnings, f"direct_llm_error:{type(exc).__name__}"],
            used_real_llm_answer=False,
        )
    answer_text = _direct_answer_text(raw)
    return RealFinalResult(
        reranked_chunks=[],
        first_pass_reranked=None,
        refused=False,
        decision_reason=DecisionReason.none,
        response_mode=ExpectedBehavior.answer,
        citations=[],
        answer_text=answer_text,
        rewrite_source="none",
        actual_rewritten_query=None,
        rewrite_model_name=None,
        rewrite_reason=None,
        second_pass_attempted=False,
        reranker_unavailable=False,
        gate_decisions={},
        agent_trace={},
        claims=[],
        warnings=warnings,
        used_real_llm_answer=True,
    )


def _direct_answer_text(raw: str) -> str:
    import json

    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and payload.get("answer_text"):
            return str(payload["answer_text"]).strip()
    except json.JSONDecodeError:
        pass
    return raw.strip()


def _trust_pass(
    case: EvalCase,
    query: str,
    retriever,
    reranker,
    *,
    evidence_gate_config: EvidenceGateConfig | None = None,
) -> RetrievalPassResult:
    gate_config = evidence_gate_config or evidence_gate_config_from_settings(get_settings())
    return run_trust_gated_pass(
        query=query,
        retrieval_options=_REAL_RUN_OPTIONS,
        retriever=retriever,
        reranker=reranker,
        user_role=case.user_role,
        user_department=case.user_department,
        user_clearance=case.user_clearance.value,
        evidence_gate_config=gate_config,
    )


def _trust_pass_with_optional_config(
    case: EvalCase,
    query: str,
    retriever,
    reranker,
    *,
    evidence_gate_config: EvidenceGateConfig | None,
) -> RetrievalPassResult:
    if evidence_gate_config is None:
        return _trust_pass(case, query, retriever, reranker)
    return _trust_pass(
        case,
        query,
        retriever,
        reranker,
        evidence_gate_config=evidence_gate_config,
    )


def _should_rewrite(
    pass_result: RetrievalPassResult,
    *,
    trust_gate_policy: str = "legacy",
) -> bool:
    if pass_result.evidence_decision.evidence_sufficient:
        return False
    if _acl_denies_required_evidence(
        pass_result,
        trust_gate_policy=trust_gate_policy,
    ):
        return False
    if pass_result.conflict_decision.has_conflict:
        return False
    if _query_targets_deprecated(
        pass_result.query, pass_result.state_decision.deprecated_chunks
    ):
        return False
    return True


def _agentic_rewrite(case: EvalCase, first_pass: RetrievalPassResult) -> RewriteDecision:
    rewriter = get_query_rewriter()
    if rewriter is None:
        return RewriteDecision(
            should_rewrite=False,
            rewritten_query=None,
            reason="no_real_rewrite_provider_configured",
            warnings=[
                "No real LLM rewrite provider is configured; final_agentic will not "
                "perform a second-pass retrieval."
            ],
            source="none",
            model_name=None,
        )
    return rewriter.rewrite(
        case.query,
        chunk_previews=first_pass.reranked_chunks[:3],
    )


def _refusal_for_pass(
    final_pass: RetrievalPassResult,
    warnings: list[str],
    *,
    trust_gate_policy: str = "legacy",
):
    permission_denied = _acl_denies_required_evidence(
        final_pass,
        trust_gate_policy=trust_gate_policy,
    )
    deprecated_warning = _deprecated_warning_for_policy(
        final_pass,
        trust_gate_policy=trust_gate_policy,
    )
    return decide_response_mode(
        state_decision=final_pass.state_decision,
        acl_decision=final_pass.acl_decision,
        conflict_decision=final_pass.conflict_decision,
        evidence_decision=final_pass.evidence_decision,
        permission_denied=permission_denied,
        deprecated_warning=deprecated_warning,
        warnings=warnings,
    )


def _refusal_for_pass_with_optional_policy(
    final_pass: RetrievalPassResult,
    warnings: list[str],
    *,
    trust_gate_policy: str,
):
    try:
        return _refusal_for_pass(
            final_pass,
            warnings,
            trust_gate_policy=trust_gate_policy,
        )
    except TypeError as exc:
        if "trust_gate_policy" not in str(exc):
            raise
        return _refusal_for_pass(final_pass, warnings)


def _refusal_text(response_mode: ExpectedBehavior) -> str:
    if response_mode == ExpectedBehavior.refuse_permission:
        return "I do not have access to the required document evidence for this request."
    if response_mode == ExpectedBehavior.report_conflict:
        return "I found conflicting active document evidence and cannot give one answer."
    if response_mode == ExpectedBehavior.warn_deprecated:
        return "The matching evidence is deprecated and should not be treated as current."
    return "I do not have enough provided evidence to answer this question."


def _decision_reason(response_mode: ExpectedBehavior) -> DecisionReason:
    if response_mode == ExpectedBehavior.refuse_no_evidence:
        return DecisionReason.no_evidence
    if response_mode == ExpectedBehavior.refuse_permission:
        return DecisionReason.permission_denied
    if response_mode == ExpectedBehavior.warn_deprecated:
        return DecisionReason.deprecated_only
    if response_mode == ExpectedBehavior.report_conflict:
        return DecisionReason.conflict_detected
    if response_mode == ExpectedBehavior.system_error:
        return DecisionReason.system_error
    return DecisionReason.none


def _gate_decisions(pass_result: RetrievalPassResult) -> dict[str, Any]:
    if not all(
        hasattr(pass_result, attr)
        for attr in (
            "evidence_decision",
            "acl_decision",
            "state_decision",
            "conflict_decision",
        )
    ):
        return {}
    return {
        "evidence_sufficient": pass_result.evidence_decision.evidence_sufficient,
        "evidence_reason": pass_result.evidence_decision.reason,
        "evidence_support_count": pass_result.evidence_decision.support_count,
        "evidence_entity_miss": pass_result.evidence_decision.entity_miss,
        "acl_surviving_count": len(pass_result.acl_decision.surviving_chunks),
        "acl_blocked_count": len(pass_result.acl_decision.blocked_chunks),
        "state_surviving_count": len(pass_result.state_decision.surviving_chunks),
        "state_deprecated_count": len(pass_result.state_decision.deprecated_chunks),
        "state_blocked_count": len(pass_result.state_decision.blocked_chunks),
        "conflict_detected": pass_result.conflict_decision.has_conflict,
        "conflict_group_id": pass_result.conflict_decision.conflict_group_id,
    }
