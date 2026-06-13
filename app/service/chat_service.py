from __future__ import annotations

import re
from typing import Any

from app.answer.answer_generator import GeneratedAnswer, GeneratedClaim, generate_answer
from app.answer.citation_binder import bind_citations
from app.answer.refusal_controller import RefusalDecision, decide_response_mode
from app.context.context_assembler import assemble_context
from app.core.config import get_settings
from app.core.enums import DecisionReason, ExpectedBehavior
from app.core.ids import make_trace_id
from app.guards.evidence_gate import evidence_gate_config_from_settings
from app.index.build_index import INDEX_METADATA_PATH, read_index_metadata
from app.index.embedding_service import get_embedding_service
from app.index.keyword_store import KeywordStore
from app.index.vector_store import VectorStore
from app.llm.llm_client import get_llm_client
from app.rerank.reranker import MOCK_RERANKER_WARNING, get_reranker
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.keyword_retriever import KeywordRetriever
from app.retrieval.llm_query_rewriter import get_query_rewriter
from app.retrieval.query_rewriter import rewrite_query_for_evidence
from app.retrieval.vector_retriever import VectorRetriever
from app.schemas.chat import ChatDecision, ChatRequest, ChatResponse
from app.schemas.retrieval import RetrievedChunk
from app.workflow.orchestrator import run_trust_gated_pass
from app.workflow.state import AgenticRecoveryState, RetrievalPassResult

_QUERY_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_DEPRECATED_QUERY_TERMS = {"deprecated", "legacy", "old", "stale", "v1"}
_TRUST_GATE_POLICY_LEGACY = "legacy"
_TRUST_GATE_POLICY_NEIGHBOR_TOLERANT = "neighbor_tolerant"
_TRUST_GATE_POLICIES = {
    _TRUST_GATE_POLICY_LEGACY,
    _TRUST_GATE_POLICY_NEIGHBOR_TOLERANT,
}


def answer_chat(request: ChatRequest) -> ChatResponse:
    trace_id = make_trace_id()
    try:
        return _answer_chat_checked(request, trace_id)
    except Exception:
        return _system_error_response(request, trace_id)


def _answer_chat_checked(request: ChatRequest, trace_id: str) -> ChatResponse:
    settings = get_settings()
    warnings: list[str] = []

    retriever = _make_hybrid_retriever()
    if getattr(retriever, "vector_retriever", None) is None:
        warnings.append(
            "Vector retriever unavailable; using keyword retrieval only for this request."
    )
    reranker = get_reranker(settings.reranker_provider)
    evidence_gate_config = evidence_gate_config_from_settings(settings)
    trust_gate_policy = _normalize_trust_gate_policy(
        getattr(settings, "trust_gate_policy", _TRUST_GATE_POLICY_LEGACY)
    )

    first_pass = run_trust_gated_pass(
        query=request.query,
        retrieval_options=request.options,
        retriever=retriever,
        reranker=reranker,
        user_role=request.user.role,
        user_department=request.user.department,
        user_clearance=request.user.clearance.value,
        evidence_gate_config=evidence_gate_config,
    )
    recovery = AgenticRecoveryState(
        original_query=request.query,
        first_pass_evidence_sufficient=first_pass.evidence_decision.evidence_sufficient,
        max_rewrite_rounds=request.options.max_rewrite_rounds,
    )
    final_pass = first_pass

    if _should_attempt_rewrite(
        request,
        first_pass,
        trust_gate_policy=trust_gate_policy,
    ):
        rewriter = get_query_rewriter()
        rewrite_decision = (
            rewriter.rewrite(
                request.query,
                chunk_previews=first_pass.reranked_chunks[:3],
            )
            if rewriter is not None
            else rewrite_query_for_evidence(request.query)
        )
        if rewrite_decision.should_rewrite and rewrite_decision.rewritten_query:
            recovery.rewrite_triggered = True
            recovery.rewritten_query = rewrite_decision.rewritten_query
            recovery.rewrite_reason = rewrite_decision.reason
            recovery.second_pass_attempted = True
            recovery.retrieval_pass_count = 2
            warnings.extend(rewrite_decision.warnings)
            final_pass = run_trust_gated_pass(
                query=rewrite_decision.rewritten_query,
                retrieval_options=request.options,
                retriever=retriever,
                reranker=reranker,
                user_role=request.user.role,
                user_department=request.user.department,
                user_clearance=request.user.clearance.value,
                evidence_gate_config=evidence_gate_config,
            )
            recovery.second_pass_evidence_sufficient = (
                final_pass.evidence_decision.evidence_sufficient
            )

    warnings.extend(first_pass.warnings)
    if final_pass is not first_pass:
        warnings.extend(final_pass.warnings)

    if settings.reranker_provider.lower() == "mock":
        warnings.append(MOCK_RERANKER_WARNING)

    permission_denied = _acl_denies_required_evidence(
        final_pass,
        trust_gate_policy=trust_gate_policy,
    )
    deprecated_warning = _deprecated_warning_for_policy(
        final_pass,
        trust_gate_policy=trust_gate_policy,
    )
    refusal = decide_response_mode(
        state_decision=final_pass.state_decision,
        acl_decision=final_pass.acl_decision,
        conflict_decision=final_pass.conflict_decision,
        evidence_decision=final_pass.evidence_decision,
        permission_denied=permission_denied,
        deprecated_warning=deprecated_warning,
        warnings=warnings,
    )

    if refusal.should_answer:
        response = _answer_from_selected_chunks(
            request=request,
            trace_id=trace_id,
            final_pass=final_pass,
            refusal=refusal,
            recovery=recovery,
            trust_gate_policy=trust_gate_policy,
            warnings=warnings,
        )
    else:
        response = _non_answer_response(
            request=request,
            trace_id=trace_id,
            final_pass=final_pass,
            refusal=refusal,
            recovery=recovery,
            trust_gate_policy=trust_gate_policy,
            warnings=warnings,
        )
    return response


def _answer_from_selected_chunks(
    *,
    request: ChatRequest,
    trace_id: str,
    final_pass: RetrievalPassResult,
    refusal: RefusalDecision,
    recovery: AgenticRecoveryState,
    trust_gate_policy: str,
    warnings: list[str],
) -> ChatResponse:
    settings = get_settings()
    context_pack = assemble_context(
        final_pass.query,
        refusal.selected_chunks,
        token_budget=settings.max_context_tokens,
        max_chunks=request.options.top_n_rerank or 0,
    )
    llm_client = get_llm_client(settings.llm_provider)
    generated_answer = generate_answer(final_pass.query, context_pack, llm_client)
    bound_answer = bind_citations(generated_answer, context_pack)
    response_warnings = [*warnings, *bound_answer.warnings]
    return _format_response(
        request=request,
        trace_id=trace_id,
        answer=bound_answer.answer_text,
        citations=bound_answer.citations,
        response_mode=ExpectedBehavior.answer,
        final_pass=final_pass,
        recovery=recovery,
        trust_gate_policy=trust_gate_policy,
        warnings=response_warnings,
        preview_chunks=refusal.selected_chunks,
    )


def _non_answer_response(
    *,
    request: ChatRequest,
    trace_id: str,
    final_pass: RetrievalPassResult,
    refusal: RefusalDecision,
    recovery: AgenticRecoveryState,
    trust_gate_policy: str,
    warnings: list[str],
) -> ChatResponse:
    answer = _refusal_answer_text(refusal.response_mode)
    citations = []
    preview_chunks: list[RetrievedChunk] = []
    if refusal.response_mode in {
        ExpectedBehavior.report_conflict,
        ExpectedBehavior.warn_deprecated,
    }:
        bound = _bind_policy_citations(answer, refusal.selected_chunks)
        citations = bound.citations
        preview_chunks = refusal.selected_chunks
    return _format_response(
        request=request,
        trace_id=trace_id,
        answer=answer,
        citations=citations,
        response_mode=refusal.response_mode,
        final_pass=final_pass,
        recovery=recovery,
        trust_gate_policy=trust_gate_policy,
        warnings=[*warnings, *refusal.warnings],
        preview_chunks=preview_chunks,
    )


def _format_response(
    *,
    request: ChatRequest,
    trace_id: str,
    answer: str,
    citations,
    response_mode: ExpectedBehavior,
    final_pass: RetrievalPassResult,
    recovery: AgenticRecoveryState,
    trust_gate_policy: str,
    warnings: list[str],
    preview_chunks: list[RetrievedChunk],
) -> ChatResponse:
    decision = ChatDecision(
        refused=response_mode != ExpectedBehavior.answer,
        reason=_decision_reason(response_mode),
        warnings=warnings,
        evidence_sufficient=final_pass.evidence_decision.evidence_sufficient,
        acl_passed=not _acl_denies_required_evidence(
            final_pass,
            trust_gate_policy=trust_gate_policy,
        ),
        state_policy=_state_policy(final_pass),
        rewrite_triggered=recovery.rewrite_triggered,
        response_mode=response_mode,
        first_pass_query=recovery.original_query,
        rewritten_query=recovery.rewritten_query,
        retrieval_pass_count=recovery.retrieval_pass_count,
        state_gate_blocked_count=len(final_pass.state_decision.blocked_chunks),
        acl_blocked_count=len(final_pass.acl_decision.blocked_chunks),
        deprecated_count=len(final_pass.state_decision.deprecated_chunks),
        conflict_detected=final_pass.conflict_decision.has_conflict,
        final_response_mode=response_mode,
        decision_reason=_decision_reason(response_mode).value,
    )

    settings = get_settings()
    provider_metadata = {
        "embedding_provider": _index_or_config_embedding_provider(),
        "reranker_provider": settings.reranker_provider,
        "reranker_model_name": settings.reranker_model_name,
        "llm_provider": settings.llm_provider,
        "llm_model_name": settings.llm_model_name,
        "mock_llm_for_local_demo_only": settings.llm_provider.lower() == "mock",
        "mock_reranker_for_tests_smoke_only": settings.reranker_provider.lower() == "mock",
        "trust_gate_policy": trust_gate_policy,
    }
    trust_trace = _trust_trace(
        final_pass,
        recovery,
        response_mode,
        trust_gate_policy=trust_gate_policy,
    )

    return ChatResponse(
        answer=answer,
        citations=citations,
        decision=decision,
        response_mode=response_mode,
        trace_id=trace_id,
        retrieved_chunks_preview=_preview_chunks(
            preview_chunks,
            request.options.return_retrieved_chunks,
        ),
        provider_metadata=provider_metadata,
        warnings=warnings,
        trust_trace=trust_trace,
    )


def _system_error_response(request: ChatRequest, trace_id: str) -> ChatResponse:
    response_mode = ExpectedBehavior.system_error
    warnings = ["A non-recoverable system error occurred during chat orchestration."]
    decision = ChatDecision(
        refused=True,
        reason=DecisionReason.system_error,
        warnings=warnings,
        evidence_sufficient=False,
        acl_passed=False,
        rewrite_triggered=False,
        response_mode=response_mode,
        first_pass_query=request.query,
        final_response_mode=response_mode,
        decision_reason=DecisionReason.system_error.value,
    )
    return ChatResponse(
        answer="I cannot answer right now because the retrieval workflow hit a system error.",
        citations=[],
        decision=decision,
        response_mode=response_mode,
        trace_id=trace_id,
        retrieved_chunks_preview=[],
        provider_metadata={},
        warnings=warnings,
        trust_trace={
            "first_pass_query": request.query,
            "rewritten_query": None,
            "rewrite_triggered": False,
            "retrieval_pass_count": 1,
            "state_gate_blocked_count": 0,
            "acl_blocked_count": 0,
            "deprecated_count": 0,
            "conflict_detected": False,
            "evidence_sufficient": False,
            "final_response_mode": response_mode.value,
            "decision_reason": DecisionReason.system_error.value,
        },
    )


def _make_hybrid_retriever() -> HybridRetriever:
    settings = get_settings()
    keyword_retriever = KeywordRetriever(KeywordStore(settings.whoosh_index_dir))
    vector_retriever = None
    try:
        embedding_provider = _index_or_config_embedding_provider()
        vector_retriever = VectorRetriever(
            get_embedding_service(embedding_provider),
            VectorStore(settings.qdrant_url, settings.qdrant_collection),
        )
    except Exception:
        vector_retriever = None
    return HybridRetriever(
        vector_retriever=vector_retriever,
        keyword_retriever=keyword_retriever,
    )


def _index_or_config_embedding_provider() -> str:
    metadata = read_index_metadata(INDEX_METADATA_PATH)
    if metadata and metadata.get("embedding_provider"):
        return str(metadata["embedding_provider"])
    return get_settings().embedding_provider


def _preview_chunks(chunks: list[RetrievedChunk], include_full: bool) -> list[RetrievedChunk]:
    if include_full:
        return chunks
    return chunks[:3]


def _should_attempt_rewrite(
    request: ChatRequest,
    pass_result: RetrievalPassResult,
    *,
    trust_gate_policy: str = _TRUST_GATE_POLICY_LEGACY,
) -> bool:
    if not request.options.enable_agentic_recovery:
        return False
    if request.options.max_rewrite_rounds <= 0:
        return False
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
        pass_result.query,
        pass_result.state_decision.deprecated_chunks,
    ):
        return False
    return True


def _acl_denies_required_evidence(
    pass_result: RetrievalPassResult,
    *,
    trust_gate_policy: str = _TRUST_GATE_POLICY_LEGACY,
) -> bool:
    blocked = pass_result.acl_decision.blocked_chunks
    if not blocked:
        return False
    if not pass_result.acl_decision.surviving_chunks:
        return True
    blocked_match_query = _chunks_match_query(pass_result.query, blocked)
    return blocked_match_query


def _deprecated_warning_for_policy(
    pass_result: RetrievalPassResult,
    *,
    trust_gate_policy: str = _TRUST_GATE_POLICY_LEGACY,
) -> bool:
    deprecated_matches_query = _query_targets_deprecated(
        pass_result.query,
        pass_result.state_decision.deprecated_chunks,
    )
    if not deprecated_matches_query:
        return False
    if _normalize_trust_gate_policy(trust_gate_policy) == _TRUST_GATE_POLICY_NEIGHBOR_TOLERANT:
        return not pass_result.evidence_decision.evidence_sufficient
    return True


def _normalize_trust_gate_policy(policy: str | None) -> str:
    normalized = (policy or _TRUST_GATE_POLICY_LEGACY).strip().lower()
    if normalized not in _TRUST_GATE_POLICIES:
        raise ValueError(f"Unsupported trust gate policy: {policy}")
    return normalized


def _query_targets_deprecated(query: str, chunks: list[RetrievedChunk]) -> bool:
    if not chunks:
        return False
    query_terms = _query_terms(query)
    return bool(query_terms & _DEPRECATED_QUERY_TERMS)


def _chunks_match_query(query: str, chunks: list[RetrievedChunk]) -> bool:
    query_terms = _query_terms(query)
    if not query_terms:
        return False
    for result in chunks:
        if query_terms & _chunk_terms(result):
            return True
    return False


def _query_terms(query: str) -> set[str]:
    return {
        token
        for token in _QUERY_TOKEN_PATTERN.findall(query.lower())
        if len(token) >= 3 or token in {"v1", "v2"}
    }


def _chunk_terms(result: RetrievedChunk) -> set[str]:
    terms = set(_QUERY_TOKEN_PATTERN.findall(result.chunk.text.lower()))
    for section in result.chunk.section_path:
        terms.update(_QUERY_TOKEN_PATTERN.findall(section.lower()))
    return terms


def _refusal_answer_text(response_mode: ExpectedBehavior) -> str:
    if response_mode == ExpectedBehavior.refuse_permission:
        return "I do not have access to the required document evidence for this request."
    if response_mode == ExpectedBehavior.report_conflict:
        return (
            "I found conflicting active document evidence, so I cannot provide a single "
            "authoritative answer."
        )
    if response_mode == ExpectedBehavior.warn_deprecated:
        return (
            "The matching evidence is deprecated and should not be treated as current "
            "policy."
        )
    if response_mode == ExpectedBehavior.refuse_no_evidence:
        return "I do not have enough provided evidence to answer this question."
    if response_mode == ExpectedBehavior.system_error:
        return "I cannot answer right now because the system hit an internal error."
    return "I do not have enough provided evidence to answer this question."


def _bind_policy_citations(answer: str, chunks: list[RetrievedChunk]):
    if not chunks:
        return bind_citations(
            GeneratedAnswer(answer_text=answer, claims=[]),
            assemble_context("", [], token_budget=0, max_chunks=0),
        )
    context_pack = assemble_context(
        answer,
        chunks,
        token_budget=get_settings().max_context_tokens,
        max_chunks=len(chunks),
    )
    generated = GeneratedAnswer(
        answer_text=answer,
        claims=[
            GeneratedClaim(
                claim_id="claim-0001",
                text=answer,
                supporting_chunk_ids=[chunk.chunk_id for chunk in context_pack.chunks],
            )
        ],
    )
    return bind_citations(generated, context_pack)


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


def _state_policy(pass_result: RetrievalPassResult) -> str | None:
    if pass_result.state_decision.deprecated_chunks:
        return "deprecated_evidence_withheld"
    if pass_result.state_decision.blocked_chunks:
        return "draft_or_archived_blocked"
    return None


def _trust_trace(
    pass_result: RetrievalPassResult,
    recovery: AgenticRecoveryState,
    response_mode: ExpectedBehavior,
    *,
    trust_gate_policy: str = _TRUST_GATE_POLICY_LEGACY,
) -> dict[str, Any]:
    return {
        "first_pass_query": recovery.original_query,
        "rewritten_query": recovery.rewritten_query,
        "rewrite_triggered": recovery.rewrite_triggered,
        "rewrite_reason": recovery.rewrite_reason,
        "retrieval_pass_count": recovery.retrieval_pass_count,
        "first_pass_evidence_sufficient": recovery.first_pass_evidence_sufficient,
        "second_pass_evidence_sufficient": recovery.second_pass_evidence_sufficient,
        "state_gate_blocked_count": len(pass_result.state_decision.blocked_chunks),
        "acl_blocked_count": len(pass_result.acl_decision.blocked_chunks),
        "deprecated_count": len(pass_result.state_decision.deprecated_chunks),
        "conflict_detected": pass_result.conflict_decision.has_conflict,
        "evidence_sufficient": pass_result.evidence_decision.evidence_sufficient,
        "trust_gate_policy": trust_gate_policy,
        "final_response_mode": response_mode.value,
        "decision_reason": _decision_reason(response_mode).value,
    }
