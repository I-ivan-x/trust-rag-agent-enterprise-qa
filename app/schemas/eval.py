from datetime import UTC, datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

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
    model_config = ConfigDict(populate_by_name=True)

    case_id: str
    query: str
    query_type: QueryType
    eval_split: EvalSplit = Field(
        default=EvalSplit.fixture,
        validation_alias=AliasChoices("split", "eval_split"),
        serialization_alias="split",
    )
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
    expected_response_mode: ExpectedBehavior | None = None
    gold_doc_ids: list[str] = Field(default_factory=list)
    gold_chunk_ids: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    reference_claims: list[str] = Field(default_factory=list)
    requires_citation: bool = Field(
        default=True,
        validation_alias=AliasChoices("requires_citation", "must_cite"),
    )
    must_cite: bool = True
    must_refuse: bool = False
    requires_real_model: bool = False

    expected_rewrite: str | None = None
    hard_negative_group_id: str | None = None
    notes: str | None = None
    attack_class: str | None = None
    success_predicate: str | None = None
    paired_control: bool = False
    benign_gold: str | None = None

    @model_validator(mode="after")
    def _normalize_compatible_fields(self) -> "EvalCase":
        self.must_cite = self.requires_citation
        if self.expected_response_mode is None:
            self.expected_response_mode = self.expected_behavior
        return self


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
