from __future__ import annotations

import json
from pathlib import Path

from app.agent.diagnosis import ActionType, FailureType, diagnose
from app.core.enums import AccessLevel, DocumentStatus
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


def test_diagnosis_sufficient_has_no_recovery_actions() -> None:
    active = make_retrieved_chunk("active", "refresh token limit")
    report = diagnose(
        _pass_result(
            reranked=[active],
            acl_surviving=[active],
            evidence_sufficient=True,
            support_count=1,
        )
    )

    assert report.evidence_decision == "sufficient"
    assert report.failure_type == FailureType.no_recovery
    assert report.legal_actions == []


def test_failure_type_space_is_frozen_to_p3_actions() -> None:
    assert {failure.value for failure in FailureType} == {
        "PERMISSION_BLOCKED",
        "CONFLICT",
        "POLICY_CROWDING",
        "WEAK_RECALL",
        "NO_RECOVERY",
    }


def test_diagnosis_permission_blocked_is_terminal() -> None:
    restricted = make_retrieved_chunk(
        "restricted",
        "restricted admin key detail",
        access_level=AccessLevel.restricted,
        allowed_roles=["security_admin"],
    )
    report = diagnose(
        _pass_result(
            reranked=[restricted],
            acl_blocked=[restricted],
            evidence_sufficient=False,
        )
    )

    assert report.failure_type == FailureType.permission_blocked
    assert report.legal_actions == [ActionType.refuse_with_explanation]


def test_diagnosis_conflict_allows_conflict_set() -> None:
    left = make_retrieved_chunk("left", "30 minutes", doc_id="doc-a", conflict_group_id="g1")
    right = make_retrieved_chunk(
        "right",
        "60 minutes",
        doc_id="doc-b",
        conflict_group_id="g1",
    )
    report = diagnose(
        _pass_result(
            reranked=[left, right],
            acl_surviving=[left, right],
            conflict_group_id="g1",
            conflicting=[left, right],
            evidence_sufficient=False,
        )
    )

    assert report.failure_type == FailureType.conflict
    assert report.conflict_group_ids == ["g1"]
    assert report.legal_actions == [
        ActionType.present_conflict_set,
        ActionType.refuse_with_explanation,
    ]


def test_diagnosis_policy_crowding_allows_filtered_retrieval() -> None:
    active = make_retrieved_chunk(
        "active",
        "current token limit",
        status=DocumentStatus.active,
    )
    deprecated = make_retrieved_chunk(
        "deprecated",
        "old token limit",
        status=DocumentStatus.deprecated,
    )
    deprecated_2 = make_retrieved_chunk(
        "deprecated-2",
        "older token limit",
        status=DocumentStatus.deprecated,
    )
    report = diagnose(
        _pass_result(
            reranked=[active, deprecated, deprecated_2],
            acl_surviving=[active],
            deprecated=[deprecated, deprecated_2],
            evidence_sufficient=False,
            top_score=0.9,
        )
    )

    assert report.failure_type == FailureType.policy_crowding
    assert report.legal_actions == [
        ActionType.filtered_retrieval,
        ActionType.refuse_with_explanation,
    ]


def test_diagnosis_policy_crowding_requires_some_clean_evidence() -> None:
    deprecated = make_retrieved_chunk(
        "deprecated",
        "old token limit",
        status=DocumentStatus.deprecated,
    )
    deprecated_2 = make_retrieved_chunk(
        "deprecated-2",
        "older token limit",
        status=DocumentStatus.deprecated,
    )
    report = diagnose(
        _pass_result(
            reranked=[deprecated, deprecated_2],
            deprecated=[deprecated, deprecated_2],
            evidence_sufficient=False,
            top_score=0.9,
        )
    )

    assert report.clean_active_count == 0
    assert report.failure_type == FailureType.no_recovery
    assert report.legal_actions == [ActionType.refuse_with_explanation]


def test_diagnosis_weak_recall_allows_rewrite() -> None:
    weak = make_retrieved_chunk("weak", "unrelated", rerank_score=0.1)
    report = diagnose(
        _pass_result(
            reranked=[weak],
            acl_surviving=[weak],
            evidence_sufficient=False,
            entity_miss=True,
            top_score=0.1,
        )
    )

    assert report.failure_type == FailureType.weak_recall
    assert report.legal_actions == [
        ActionType.rewrite_query,
        ActionType.refuse_with_explanation,
    ]


def test_diagnosis_policy_crowding_and_weak_signal_allows_a_b_e() -> None:
    active = make_retrieved_chunk(
        "active",
        "current token limit",
        status=DocumentStatus.active,
        rerank_score=0.1,
    )
    deprecated = make_retrieved_chunk(
        "deprecated",
        "old token limit",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )
    deprecated_2 = make_retrieved_chunk(
        "deprecated-2",
        "older token limit",
        status=DocumentStatus.deprecated,
        rerank_score=0.1,
    )
    report = diagnose(
        _pass_result(
            reranked=[active, deprecated, deprecated_2],
            acl_surviving=[active],
            deprecated=[deprecated, deprecated_2],
            evidence_sufficient=False,
            entity_miss=True,
            top_score=0.1,
        )
    )

    assert report.failure_type == FailureType.policy_crowding
    assert report.legal_actions == [
        ActionType.rewrite_query,
        ActionType.filtered_retrieval,
        ActionType.refuse_with_explanation,
    ]


def test_diagnosis_no_recovery_defaults_to_refuse() -> None:
    neutral = make_retrieved_chunk("neutral", "some adjacent evidence")
    report = diagnose(
        _pass_result(
            reranked=[neutral],
            acl_surviving=[neutral],
            evidence_sufficient=False,
            entity_miss=False,
            top_score=0.9,
        )
    )

    assert report.failure_type == FailureType.no_recovery
    assert report.legal_actions == [ActionType.refuse_with_explanation]


def test_current_p3_09_precheck_cases_match_report_anchor() -> None:
    json_path = Path("data/eval_runs/p3-09-diagnostic-precheck/diagnostic_precheck.json")
    report_path = Path("docs/P3_09_DIAGNOSTIC_PRECHECK.md")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    cases = payload["cases"]
    report_rows = _p3_09_report_rows(report_path)

    assert len(cases) == 33
    assert len(report_rows) == 33
    assert payload["summary"]["llm_call_count"] == 0
    assert payload["summary"]["llm_usage_total_tokens"] == 0
    assert (
        payload["summary"]["residual_action_profile"]["action_b_filtered_retrieval"][
            "gold_doc_recoverable_count"
        ]
        == 0
    )

    for record in cases:
        key = (record["split"], record["case_id"])
        expected = report_rows[key]
        FailureType(record["failure_type"])
        for action in record["legal_actions"]:
            ActionType(action)

        assert record["failure_type"] == expected["failure_type"]
        assert _legal_key(record["legal_actions"]) == expected["legal_actions"]
        assert record["signals"]["clean_active_count"] == expected["clean"]
        policy_count = (
            record["signals"]["deprecated_neighbor_count"]
            + record["signals"]["restricted_neighbor_count"]
        )
        assert policy_count == expected["policy"]
        assert record["signals"]["entity_miss"] is expected["entity_miss"]
        assert record["action_a"]["legal_triggered"] is expected["a"]
        assert record["action_b"]["legal_triggered"] is expected["b_legal"]
        assert record["action_b"]["recoverable"] is expected["b_save"]
        assert record["action_b"]["gold_doc_recoverable"] is False
        assert record["action_d"]["conflict_surface"] is expected["d_surface"]
        assert record["action_d"]["legal_triggered"] is expected["d_legal"]
        assert record["gold_doc_hit_at_5"] is expected["gold_doc_at_5"]


def _pass_result(
    *,
    reranked,
    acl_surviving=None,
    acl_blocked=None,
    deprecated=None,
    evidence_sufficient: bool,
    entity_miss: bool = False,
    support_count: int = 0,
    top_score: float | None = None,
    conflict_group_id: str | None = None,
    conflicting=None,
) -> RetrievalPassResult:
    if top_score is not None:
        reranked = [item.model_copy(update={"rerank_score": top_score}) for item in reranked]
    return RetrievalPassResult(
        query="What is the token limit?",
        retrieved_chunks=reranked,
        reranked_chunks=reranked,
        state_decision=StateGateDecision(
            surviving_chunks=[
                item for item in reranked if item.chunk.status == DocumentStatus.active
            ],
            deprecated_chunks=deprecated or [],
        ),
        acl_decision=ACLGateDecision(
            surviving_chunks=acl_surviving or [],
            blocked_chunks=acl_blocked or [],
        ),
        conflict_decision=ConflictDecision(
            has_conflict=bool(conflict_group_id),
            conflict_group_id=conflict_group_id,
            conflicting_chunks=conflicting or [],
        ),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=evidence_sufficient,
            reason="sufficient" if evidence_sufficient else "test",
            top_score=top_score,
            support_count=support_count,
            entity_miss=entity_miss,
        ),
    )


def _p3_09_report_rows(path: Path) -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    in_table = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("| split | case_id |"):
            in_table = True
            continue
        if not in_table or raw_line.startswith("| ---"):
            continue
        if not raw_line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in raw_line.strip("|").split("|")]
        split = cells[0].strip("`")
        case_id = cells[1].strip("`")
        rows[(split, case_id)] = {
            "failure_type": cells[2].strip("`"),
            "legal_actions": cells[3].strip("`"),
            "clean": int(cells[4]),
            "policy": int(cells[5]),
            "entity_miss": _bool_cell(cells[6]),
            "a": _bool_cell(cells[7]),
            "b_legal": _bool_cell(cells[8]),
            "b_save": _bool_cell(cells[9]),
            "d_surface": _bool_cell(cells[10]),
            "d_legal": _bool_cell(cells[11]),
            "gold_doc_at_5": _bool_cell(cells[12]),
        }
    return rows


def _legal_key(actions: list[str]) -> str:
    return ",".join(actions) if actions else "none"


def _bool_cell(value: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise AssertionError(f"not a boolean cell: {value}")
