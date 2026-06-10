import json

import pytest
from pydantic import ValidationError

from app.core.enums import (
    AccessLevel,
    CitationSupportType,
    CitationVerificationStatus,
    CorpusSource,
    DecisionReason,
    DocumentStatus,
    DocumentType,
    EvalSplit,
    ExpectedBehavior,
    MetadataOrigin,
    QuerySource,
    QueryStyle,
    QueryType,
    RetrievalSource,
    SourceOrigin,
)
from app.schemas.chat import ChatDecision, ChatRequest, ChatResponse
from app.schemas.chunk import Chunk
from app.schemas.citation import Citation, CitationLocator
from app.schemas.document import DocumentMetadata
from app.schemas.eval import EvalCase
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk, UserScope
from app.schemas.trace import AgenticRecoveryTrace, TraceRecord, TraceStep


def make_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        doc_id="doc-api-auth-service-v2",
        title="Auth Service API v2",
        doc_type=DocumentType.api_spec,
        status=DocumentStatus.active,
        version="v2",
        source_path="data/sample_corpus/api/auth_service_v2.md",
        access_level=AccessLevel.internal,
    )


def make_chunk() -> Chunk:
    return Chunk(
        chunk_id="doc-api-auth-service-v2::chunk-0001",
        doc_id="doc-api-auth-service-v2",
        chunk_index=1,
        text="The access token lifetime is 30 minutes.",
        section_path=["Auth Service API v2", "Token Lifetime"],
        heading_level=2,
        token_count=8,
        char_count=40,
        line_start=10,
        line_end=12,
        parent_section_id="sec-token-lifetime",
        status=DocumentStatus.active,
        version="v2",
        allowed_roles=["employee"],
        access_level=AccessLevel.internal,
    )


def make_user() -> UserScope:
    return UserScope(
        user_id="user-001",
        role="employee",
        department="Engineering",
        clearance=AccessLevel.internal,
    )


def make_citation() -> Citation:
    return Citation(
        citation_id="CIT-0001",
        doc_id="doc-api-auth-service-v2",
        chunk_id="doc-api-auth-service-v2::chunk-0001",
        title="Auth Service API v2",
        section_path=["Auth Service API v2", "Token Lifetime"],
        locator=CitationLocator(
            line_start=10,
            line_end=12,
            source_path="data/sample_corpus/api/auth_service_v2.md",
        ),
        support_type=CitationSupportType.direct,
        verification_status=CitationVerificationStatus.supported,
    )


def test_document_metadata_can_be_created_with_corpus_fields() -> None:
    metadata = make_metadata()

    assert metadata.corpus_source == CorpusSource.synthetic_fixture
    assert metadata.metadata_origin == MetadataOrigin.native
    assert metadata.source_origin == SourceOrigin.generated
    assert metadata.allowed_roles == ["employee"]


def test_chunk_can_be_created() -> None:
    chunk = make_chunk()

    assert chunk.doc_id == "doc-api-auth-service-v2"
    assert chunk.corpus_source == CorpusSource.synthetic_fixture


def test_chat_request_and_response_can_be_created() -> None:
    chunk = make_chunk()
    retrieved = RetrievedChunk(chunk=chunk, source=RetrievalSource.hybrid, rank=1)
    request = ChatRequest(
        query="What is the token lifetime?",
        user=make_user(),
        options=RetrievalOptions(max_rewrite_rounds=1),
        session_id="session-001",
    )
    decision = ChatDecision(
        refused=False,
        reason=DecisionReason.none,
        response_mode=ExpectedBehavior.answer,
    )
    response = ChatResponse(
        answer="The access token lifetime is 30 minutes.",
        citations=[make_citation()],
        decision=decision,
        trace_id="trace-20260610-test",
        retrieved_chunks_preview=[retrieved],
    )

    assert request.options.enable_agentic_recovery is True
    assert response.citations[0].citation_id == "CIT-0001"


def test_chat_decision_rejects_unsupported_clarification_mode() -> None:
    with pytest.raises(ValidationError):
        ChatDecision(response_mode="ask_clarification")


def test_eval_case_can_be_created_with_v03_fields() -> None:
    case = EvalCase(
        case_id="demo-001",
        query="What is the token lifetime?",
        query_type=QueryType.single_doc_fact,
        eval_split=EvalSplit.fixture,
        corpus_source=CorpusSource.synthetic_fixture,
        query_source=QuerySource.manifest_authored,
        title_overlap_score=None,
        query_style=QueryStyle.standard,
        user_role="employee",
        user_department="Engineering",
        user_clearance=AccessLevel.internal,
        expected_behavior=ExpectedBehavior.answer,
        gold_doc_ids=["doc-api-auth-service-v2"],
        gold_chunk_ids=[],
        requires_real_model=False,
    )

    assert case.eval_split == EvalSplit.fixture
    assert case.query_source == QuerySource.manifest_authored
    assert case.query_style == QueryStyle.standard
    assert case.title_overlap_score is None


def test_trace_record_can_be_created_with_agentic_recovery() -> None:
    decision = ChatDecision(response_mode=ExpectedBehavior.answer)
    trace = TraceRecord(
        trace_id="trace-20260610-test",
        session_id="session-001",
        query="What is the token lifetime?",
        user=make_user(),
        steps=[TraceStep(step_name="mock-retrieval")],
        agentic_recovery=AgenticRecoveryTrace(
            original_query="What is the token lifetime?",
            first_pass_evidence_sufficient=True,
            max_rewrite_rounds=1,
        ),
        decision=decision,
        latency_ms=12.5,
    )

    assert trace.agentic_recovery.max_rewrite_rounds == 1
    assert trace.agentic_recovery.rewrite_triggered is False


def test_json_round_trip_for_schema_models() -> None:
    metadata = make_metadata()
    metadata_round_trip = DocumentMetadata.model_validate_json(metadata.model_dump_json())
    assert metadata_round_trip == metadata

    response = ChatResponse(
        answer="The access token lifetime is 30 minutes.",
        citations=[make_citation()],
        decision=ChatDecision(response_mode=ExpectedBehavior.answer),
        trace_id="trace-20260610-test",
        retrieved_chunks_preview=[
            RetrievedChunk(chunk=make_chunk(), source=RetrievalSource.hybrid, rank=1)
        ],
    )
    response_round_trip = ChatResponse.model_validate_json(response.model_dump_json())
    assert response_round_trip == response

    case_payload = {
        "case_id": "demo-001",
        "query": "What is the token lifetime?",
        "query_type": "single_doc_fact",
        "eval_split": "fixture",
        "corpus_source": "synthetic_fixture",
        "query_source": "manifest_authored",
        "query_style": "standard",
        "user_role": "employee",
        "user_department": "Engineering",
        "user_clearance": "internal",
        "expected_behavior": "answer",
        "gold_doc_ids": ["doc-api-auth-service-v2"],
        "gold_chunk_ids": [],
        "requires_real_model": False,
    }
    case = EvalCase.model_validate_json(json.dumps(case_payload))
    assert EvalCase.model_validate_json(case.model_dump_json()) == case

