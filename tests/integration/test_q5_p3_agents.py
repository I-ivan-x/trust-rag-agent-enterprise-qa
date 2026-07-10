from __future__ import annotations

import json

import pytest

from app.govern.conditions import ConditionReport, GovernanceAction, OpsCondition
from app.govern.q5_environment import Q5ReadOnlyEnvironment
from app.govern.q5_loop import Q5AgentRuntime, Q5AgentSystem, run_q5_agent
from app.govern.sinks import LocalJsonlSink
from app.guards.acl_gate import ACLGateDecision
from app.guards.conflict_detector import ConflictDecision
from app.guards.document_state_gate import StateGateDecision
from app.guards.evidence_gate import EvidenceGateDecision
from app.schemas.q5_task import (
    Q5ActorClaims,
    Q5EnvironmentState,
    Q5ObservationTool,
    Q5TaskInput,
)
from app.workflow.state import RetrievalPassResult
from tests.helpers import make_retrieved_chunk


class DeterministicQueueModel:
    def __init__(self) -> None:
        self.outputs = [
            json.dumps(
                {
                    "kind": "observe",
                    "tool": "lookup_policy_exception",
                    "args": {
                        "resource_ref": "resource:payments",
                        "policy_ref": "policy:change-control",
                    },
                    "action": None,
                    "evidence_chunk_ids": ["q5-p3-evidence"],
                    "reason_code": "check_exception",
                    "reason_summary": "The policy exception state must be observed.",
                }
            ),
            json.dumps(
                {
                    "kind": "terminal",
                    "tool": None,
                    "args": {},
                    "action": "open_remediation_ticket",
                    "evidence_chunk_ids": ["q5-p3-evidence"],
                    "reason_code": "remediate_violation",
                    "reason_summary": "The expired exception requires remediation.",
                }
            ),
        ]
        self.calls = 0

    def generate(self, prompt: str) -> str:
        assert "RUNTIME_CONTEXT" in prompt
        self.calls += 1
        return self.outputs.pop(0)


@pytest.mark.parametrize(
    "system",
    [Q5AgentSystem.rule, Q5AgentSystem.llm, Q5AgentSystem.hybrid],
)
def test_q5_p3_agents_run_same_mock_environment_and_q4_sink(
    system: Q5AgentSystem,
    tmp_path,
) -> None:
    evidence = make_retrieved_chunk(
        "q5-p3-evidence",
        "resource:payments violates policy:change-control without an active exception.",
        doc_id="doc-q5-p3",
        rerank_score=0.95,
    )
    pass_result = RetrievalPassResult(
        query="Check the payments exception and remediate if expired.",
        retrieved_chunks=[evidence],
        reranked_chunks=[evidence],
        state_decision=StateGateDecision(surviving_chunks=[evidence]),
        acl_decision=ACLGateDecision(surviving_chunks=[evidence]),
        conflict_decision=ConflictDecision(),
        evidence_decision=EvidenceGateDecision(
            evidence_sufficient=True,
            reason="sufficient",
            top_score=0.95,
            support_count=1,
        ),
    )
    task = Q5TaskInput(
        case_id=f"q5-p3-{system.value}",
        query=pass_result.query,
        actor=Q5ActorClaims(role="admin", clearance="internal", department="sre"),
        requested_capability="remediation_management",
        resource_refs=["resource:payments", "policy:change-control"],
        available_tools=[Q5ObservationTool.lookup_policy_exception],
        corpus_namespace="q5_dev_fixture",
        environment_ref="q5-p3-env",
        max_observation_steps=2,
        max_terminal_actions=1,
    )
    environment = Q5ReadOnlyEnvironment.from_state(
        Q5EnvironmentState(
            environment_ref="q5-p3-env",
            policy_exceptions={
                "resource:payments|policy:change-control": {
                    "status": "expired",
                    "scope": "staging",
                }
            },
            change_states={},
            incident_impacts={},
            initial_records=[],
        )
    )
    model = None if system is Q5AgentSystem.rule else DeterministicQueueModel()
    result = run_q5_agent(
        system=system,
        task=task,
        pass_result=pass_result,
        report=ConditionReport(
            conditions=[OpsCondition.config_violation],
            authorized_actor=False,
            evidence_decision="sufficient",
            violating_doc_ids=["doc-q5-p3"],
        ),
        runtime=Q5AgentRuntime(
            environment=environment,
            sink=LocalJsonlSink(tmp_path / system.value),
            model=model,
        ),
    )

    assert result.final_action is GovernanceAction.open_remediation_ticket
    assert result.q4_validation.ok is True
    assert result.record is not None
    assert result.record.approval_state == "pending_approval"
    assert result.observation_count == 1
    assert result.terminal_proposal_count == 1
    assert result.step_count == 2
    assert len(result.tool_events) == len(result.otel_spans) == 1
