from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import (
    AccessLevel,
    CorpusSource,
    DecisionReason,
    EvalSplit,
    ExpectedBehavior,
    QuerySource,
    QueryStyle,
    QueryType,
)


class EvalCase(BaseModel):
    case_id: str
    query: str
    query_type: QueryType
    eval_split: EvalSplit = EvalSplit.fixture
    corpus_source: CorpusSource = CorpusSource.synthetic_fixture
    query_source: QuerySource = QuerySource.manifest_authored
    query_source_url: str | None = None
    title_overlap_score: float | None = None
    query_style: QueryStyle = QueryStyle.standard
    derived_from_case_id: str | None = None

    user_role: str = "employee"
    user_department: str | None = None
    user_clearance: AccessLevel = AccessLevel.internal

    expected_behavior: ExpectedBehavior
    gold_doc_ids: list[str] = Field(default_factory=list)
    gold_chunk_ids: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    must_cite: bool = True
    must_refuse: bool = False
    requires_real_model: bool = False

    expected_rewrite: str | None = None
    hard_negative_group_id: str | None = None


class EvalResult(BaseModel):
    case_id: str
    system_name: str
    eval_split: EvalSplit
    corpus_source: CorpusSource
    raw_correct: bool | None = None
    grounded_correct: bool | None = None
    citation_valid: bool | None = None
    refused: bool
    decision_reason: DecisionReason = DecisionReason.none
    rewrite_triggered: bool = False
    trace_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class EvalRunSummary(BaseModel):
    run_id: str
    systems: list[str] = Field(default_factory=list)
    eval_split: EvalSplit
    num_cases: int = Field(ge=0)
    summary_metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    uses_real_embedding: bool = False
    uses_real_reranker: bool = False
    uses_real_llm: bool = False

