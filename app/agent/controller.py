from __future__ import annotations

from app.agent.actions import ActionProposal
from app.agent.diagnosis import ActionType, DiagnosisReport, FailureType


class RuleController:
    def select(self, diagnosis: DiagnosisReport) -> ActionProposal:
        if diagnosis.failure_type == FailureType.permission_blocked:
            return _refuse(diagnosis)
        if diagnosis.failure_type == FailureType.conflict:
            return ActionProposal(
                action=ActionType.present_conflict_set,
                args={"conflict_group_ids": diagnosis.conflict_group_ids},
                source="rule",
            )
        # TODO-W7: co-occurrence priority defaults to filtered_retrieval > rewrite_query.
        if ActionType.filtered_retrieval in diagnosis.legal_actions:
            return ActionProposal(
                action=ActionType.filtered_retrieval,
                args={},
                source="rule",
            )
        if ActionType.rewrite_query in diagnosis.legal_actions:
            return ActionProposal(action=ActionType.rewrite_query, args={}, source="rule")
        return _refuse(diagnosis)


def _refuse(diagnosis: DiagnosisReport) -> ActionProposal:
    return ActionProposal(
        action=ActionType.refuse_with_explanation,
        args={"reason": diagnosis.failure_type.value},
        source="rule",
    )
