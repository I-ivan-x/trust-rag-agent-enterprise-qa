from __future__ import annotations

import inspect
import json
from typing import Any

from app.govern.conditions import ConditionReport, GovernanceAction
from app.govern.controller import GovernanceControllerContext, GovernanceRuleController
from app.govern.validator import GovernanceProposal, legal_actions_for_report
from app.llm.llm_client import BaseLLMClient, safe_json_loads


class GovernanceLLMController:
    controller_source = "llm"

    def __init__(
        self,
        llm_client: BaseLLMClient,
        *,
        fallback: GovernanceRuleController | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.fallback = fallback or GovernanceRuleController()

    def select(
        self,
        report: ConditionReport,
        context: GovernanceControllerContext,
    ) -> GovernanceProposal:
        prompt = build_governance_prompt(report, context)
        raw = _generate_temperature_zero(self.llm_client, prompt)
        payload = safe_json_loads(raw)
        if payload is None:
            return self._fallback(report, context, "parse_error", None)

        raw_proposal = dict(payload)
        action_value = payload.get("action")
        args = payload.get("args")
        if not isinstance(action_value, str) or not isinstance(args, dict):
            return self._fallback(report, context, "parse_error", raw_proposal)

        try:
            action = GovernanceAction(action_value)
        except ValueError:
            return self._fallback(report, context, "illegal_action", raw_proposal)

        if action not in legal_actions_for_report(report):
            return self._fallback(report, context, "illegal_action", raw_proposal)

        reason = payload.get("reason")
        return GovernanceProposal(
            action=action,
            args=args,
            source="llm",
            reason=str(reason).strip() if reason else None,
            controller_source=self.controller_source,
            llm_raw_proposal=raw_proposal,
            accepted=True,
        )

    def _fallback(
        self,
        report: ConditionReport,
        context: GovernanceControllerContext,
        reason: str,
        raw_proposal: dict[str, Any] | None,
    ) -> GovernanceProposal:
        proposal = self.fallback.select(report, context)
        return proposal.model_copy(
            update={
                "source": "llm_fallback_rule",
                "controller_source": self.controller_source,
                "llm_raw_proposal": raw_proposal,
                "accepted": False,
                "fallback_reason": reason,
            }
        )


def build_governance_prompt(
    report: ConditionReport,
    context: GovernanceControllerContext,
) -> str:
    legal_actions = [action.value for action in legal_actions_for_report(report)]
    signals = {
        "conditions": [condition.value for condition in report.conditions],
        "authorized_actor": report.authorized_actor,
        "evidence_decision": report.evidence_decision,
        "stale_doc_ids": report.stale_doc_ids,
        "violating_doc_ids": report.violating_doc_ids,
        "conflict_group_ids": report.conflict_group_ids,
        "broken_xref_doc_ids": report.broken_xref_doc_ids,
        "permission_blocked_count": report.permission_blocked_count,
    }
    return "\n".join(
        [
            "You choose exactly ONE governance action for an evidence-aware ops copilot.",
            "You may ONLY choose from LEGAL_ACTIONS.",
            "Do not output a risk field. Any risk value you output will be ignored; "
            "risk tier is fixed by code.",
            f"QUERY: {context.query}",
            f"LEGAL_ACTIONS: {json.dumps(legal_actions, ensure_ascii=False)}",
            f"SIGNALS: {json.dumps(signals, ensure_ascii=False, sort_keys=True)}",
            "NEIGHBORHOOD:",
            json.dumps(context.neighborhood, ensure_ascii=False, sort_keys=True),
            "Return JSON only with this shape:",
            '{"action":"<one of LEGAL_ACTIONS>","args":{},"reason":"<= 1 sentence"}',
            "Args may include doc_ids and evidence_citations, but citations must be "
            "chunk_id values from NEIGHBORHOOD only.",
        ]
    )


def _generate_temperature_zero(llm_client: BaseLLMClient, prompt: str) -> str:
    generate = llm_client.generate
    try:
        signature = inspect.signature(generate)
    except (TypeError, ValueError):
        return generate(prompt)
    parameters = signature.parameters.values()
    supports_temperature = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD or parameter.name == "temperature"
        for parameter in parameters
    )
    if supports_temperature:
        return generate(prompt, temperature=0)
    return generate(prompt)
