from __future__ import annotations

from app.answer.answer_generator import generate_answer
from app.answer.citation_binder import bind_citations
from app.context.context_assembler import assemble_context
from app.core.config import get_settings
from app.core.enums import DecisionReason, ExpectedBehavior
from app.core.ids import make_trace_id
from app.index.build_index import INDEX_METADATA_PATH, read_index_metadata
from app.index.embedding_service import get_embedding_service
from app.index.keyword_store import KeywordStore
from app.index.vector_store import VectorStore
from app.llm.llm_client import get_llm_client
from app.rerank.reranker import MOCK_RERANKER_WARNING, get_reranker
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.keyword_retriever import KeywordRetriever
from app.retrieval.vector_retriever import VectorRetriever
from app.schemas.chat import ChatDecision, ChatRequest, ChatResponse
from app.schemas.retrieval import RetrievedChunk


def answer_chat(request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    trace_id = make_trace_id()
    warnings: list[str] = []

    retriever = _make_hybrid_retriever()
    if getattr(retriever, "vector_retriever", None) is None:
        warnings.append(
            "Vector retriever unavailable; using keyword retrieval only for this request."
        )
    retrieved_chunks = retriever.retrieve(request.query, request.options)
    warnings.extend(retriever.last_warnings)

    reranker = get_reranker(settings.reranker_provider)
    reranked_chunks = reranker.rerank(
        request.query,
        retrieved_chunks,
        top_n=request.options.top_n_rerank,
    )
    context_pack = assemble_context(
        request.query,
        reranked_chunks,
        token_budget=settings.max_context_tokens,
        max_chunks=request.options.top_n_rerank or 0,
    )
    llm_client = get_llm_client(settings.llm_provider)
    generated_answer = generate_answer(request.query, context_pack, llm_client)
    bound_answer = bind_citations(generated_answer, context_pack)
    warnings.extend(bound_answer.warnings)

    response_mode = generated_answer.response_mode
    if settings.reranker_provider.lower() == "mock":
        warnings.append(MOCK_RERANKER_WARNING)

    decision = ChatDecision(
        refused=response_mode != ExpectedBehavior.answer,
        reason=(
            DecisionReason.no_evidence
            if response_mode == ExpectedBehavior.refuse_no_evidence
            else DecisionReason.none
        ),
        warnings=warnings,
        evidence_sufficient=bool(context_pack.chunks),
        acl_passed=True,
        rewrite_triggered=False,
        response_mode=response_mode,
    )

    provider_metadata = {
        "embedding_provider": _index_or_config_embedding_provider(),
        "reranker_provider": settings.reranker_provider,
        "reranker_model_name": settings.reranker_model_name,
        "llm_provider": settings.llm_provider,
        "llm_model_name": settings.llm_model_name,
        "mock_llm_for_local_demo_only": settings.llm_provider.lower() == "mock",
        "mock_reranker_for_tests_smoke_only": settings.reranker_provider.lower() == "mock",
    }

    return ChatResponse(
        answer=bound_answer.answer_text,
        citations=bound_answer.citations,
        decision=decision,
        response_mode=response_mode,
        trace_id=trace_id,
        retrieved_chunks_preview=_preview_chunks(
            reranked_chunks,
            request.options.return_retrieved_chunks,
        ),
        provider_metadata=provider_metadata,
        warnings=warnings,
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
