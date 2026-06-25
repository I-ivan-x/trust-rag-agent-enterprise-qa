from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.eval.govern_runner import run_governance_case
from app.govern.approvals import approve_pending, list_pending, reject_pending
from app.govern.controller import GovernanceRuleController
from app.govern.llm_controller import GovernanceLLMController
from app.govern.sinks import ActionRecord, LocalJsonlSink
from app.guards.evidence_gate import evidence_gate_config_from_settings
from app.llm.llm_client import get_llm_client
from app.rerank.reranker import get_reranker
from app.schemas.eval import EvalCase
from app.service.chat_service import _make_hybrid_retriever

router = APIRouter(prefix="/govern", tags=["governance"])
ControllerName = Literal["rule", "llm"]

DEMO_ACTION_STORE_DIR = Path("data/action_store_demo")


class GovernRunRequest(BaseModel):
    query: str = Field(min_length=1)
    user_role: str = Field(min_length=1)
    user_clearance: str = "internal"
    user_department: str | None = None
    controller: ControllerName | None = None


class GovernRunResponse(BaseModel):
    result: dict[str, Any]
    trace: dict[str, Any]


def get_govern_sink() -> LocalJsonlSink:
    return LocalJsonlSink(DEMO_ACTION_STORE_DIR)


def get_govern_retriever():
    return _make_hybrid_retriever()


def get_govern_reranker():
    return get_reranker()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SinkDep = Annotated[LocalJsonlSink, Depends(get_govern_sink)]
RetrieverDep = Annotated[Any, Depends(get_govern_retriever)]
RerankerDep = Annotated[Any, Depends(get_govern_reranker)]


@router.post("/run", response_model=GovernRunResponse)
def run_governance(
    request: GovernRunRequest,
    settings: SettingsDep,
    sink: SinkDep,
    retriever: RetrieverDep,
    reranker: RerankerDep,
    controller: Annotated[ControllerName | None, Query()] = None,
) -> GovernRunResponse:
    selected_controller = request.controller or controller or "rule"
    case = _case_from_request(request)
    row = run_governance_case(
        case,
        _controller(selected_controller, settings),
        retriever,
        reranker,
        settings,
        system_name=f"demo_governed_{selected_controller}",
        run_index=1,
        evidence_gate_config=evidence_gate_config_from_settings(settings),
        sink=sink,
    )
    return GovernRunResponse(result=row["result"], trace=row["trace"])


@router.get("/pending", response_model=list[ActionRecord])
def pending_actions(sink: SinkDep) -> list[ActionRecord]:
    return list_pending(sink)


@router.post("/pending/{record_id}/approve", response_model=ActionRecord)
def approve_action(record_id: str, sink: SinkDep) -> ActionRecord:
    try:
        return approve_pending(record_id, sink)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/pending/{record_id}/reject", response_model=ActionRecord)
def reject_action(record_id: str, sink: SinkDep) -> ActionRecord:
    try:
        return reject_pending(record_id, sink)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/audit", response_model=list[ActionRecord])
def audit_actions(sink: SinkDep) -> list[ActionRecord]:
    return _sorted_records(sink.list_records())


@router.get("/audit/blocked", response_model=list[ActionRecord])
def blocked_actions(sink: SinkDep) -> list[ActionRecord]:
    return [
        record
        for record in _sorted_records(sink.list_records())
        if record.approval_state == "escalated"
    ]


def _case_from_request(request: GovernRunRequest) -> EvalCase:
    return EvalCase(
        case_id="govern-demo",
        split="fixture",
        query=request.query,
        query_type="unknown",
        corpus_source="synthetic_fixture",
        user_role=request.user_role,
        user_department=request.user_department,
        user_clearance=request.user_clearance,
        expected_behavior="answer",
        gold_doc_ids=[],
        requires_citation=True,
        gold_condition="none",
        secondary_conditions=[],
        gold_action="no_op",
        authorized=True,
        expected_tier="none",
    )


def _controller(name: ControllerName, settings: Settings):
    if name == "rule":
        return GovernanceRuleController()
    return GovernanceLLMController(
        get_llm_client(
            settings.llm_provider,
            temperature=0,
            purpose="controller",
        ),
        fallback=GovernanceRuleController(),
    )


def _sorted_records(records: list[ActionRecord]) -> list[ActionRecord]:
    return sorted(records, key=lambda record: (record.created_at, record.record_id))
