from __future__ import annotations

import inspect
import json
from typing import Any

from app.agent.actions import ActionProposal
from app.agent.controller import ControllerContext, RuleController
from app.agent.diagnosis import ActionType, DiagnosisReport
from app.llm.llm_client import BaseLLMClient, safe_json_loads


class LLMController:
    controller_source = "llm"

    def __init__(
        self,
        llm_client: BaseLLMClient,
        *,
        fallback: RuleController | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.fallback = fallback or RuleController()

    def select(
        self,
        diagnosis: DiagnosisReport,
        context: ControllerContext,
    ) -> ActionProposal:
        prompt = build_prompt(diagnosis, context)
        raw = _generate_temperature_zero(self.llm_client, prompt)
        payload = safe_json_loads(raw)
        if payload is None:
            return self._fallback(diagnosis, context, "parse_error", None)

        raw_proposal = _raw_proposal(payload)
        action_value = payload.get("action")
        args = payload.get("args")
        if not isinstance(action_value, str) or not isinstance(args, dict):
            return self._fallback(
                diagnosis,
                context,
                "parse_error",
                raw_proposal,
            )

        try:
            action = ActionType(action_value)
        except ValueError:
            return self._fallback(
                diagnosis,
                context,
                "parse_error",
                raw_proposal,
            )

        reason = payload.get("reason")
        return ActionProposal(
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
        diagnosis: DiagnosisReport,
        context: ControllerContext,
        reason: str,
        raw_proposal: dict[str, Any] | None,
    ) -> ActionProposal:
        proposal = self.fallback.select(diagnosis, context)
        return proposal.model_copy(
            update={
                "source": "llm_fallback_rule",
                "controller_source": self.controller_source,
                "llm_raw_proposal": raw_proposal,
                "accepted": False,
                "fallback_reason": reason,
            }
        )


def build_prompt(diagnosis: DiagnosisReport, context: ControllerContext) -> str:
    legal_actions = [action.value for action in diagnosis.legal_actions]
    signals = {
        "deprecated_neighbors": diagnosis.deprecated_neighbor_count,
        "restricted_neighbors": diagnosis.restricted_neighbor_count,
        "clean_active": diagnosis.clean_active_count,
        "top_rerank_score": diagnosis.top_rerank_score,
        "entity_miss": diagnosis.entity_miss,
        "permission_blocked": diagnosis.permission_blocked_count,
        "support_chunks": diagnosis.support_chunk_count,
        "conflict_group_ids": diagnosis.conflict_group_ids,
    }
    return "\n".join(
        [
            "You choose exactly ONE recovery action for a retrieval-augmented QA "
            "system that found INSUFFICIENT evidence.",
            "You may ONLY choose from LEGAL_ACTIONS.",
            "You cannot bypass access-control or document-state controls; filters "
            "may only narrow.",
            f"QUERY: {context.query}",
            f"FAILURE_TYPE: {diagnosis.failure_type.value}",
            f"LEGAL_ACTIONS: {json.dumps(legal_actions, ensure_ascii=False)}",
            f"SIGNALS: {json.dumps(signals, ensure_ascii=False, sort_keys=True)}",
            "NEIGHBORHOOD_TOP_RETRIEVED:",
            json.dumps(context.neighborhood, ensure_ascii=False, sort_keys=True),
            "Return JSON only with this shape:",
            '{"action":"<one of LEGAL_ACTIONS>","args":{},"reason":"<= 1 sentence"}',
            "Args by action: rewrite_query uses {\"rewritten_query\": str}; "
            "filtered_retrieval uses {\"filters\":{\"status\"?:\"active\","
            "\"exclude_doc_ids\"?: [doc ids from NEIGHBORHOOD_TOP_RETRIEVED]}}; "
            "present_conflict_set uses {\"conflict_group_ids\": list}; "
            "refuse_with_explanation uses {\"reason\": str}.",
            "Rules: action MUST be in LEGAL_ACTIONS. filtered_retrieval filters "
            "may only tighten. rewrite_query must not introduce entities absent "
            "from QUERY or NEIGHBORHOOD_TOP_RETRIEVED.",
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
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        or parameter.name == "temperature"
        for parameter in parameters
    )
    if supports_temperature:
        return generate(prompt, temperature=0)
    return generate(prompt)


def _raw_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    args = payload.get("args")
    return {
        "action": payload.get("action"),
        "args": args if isinstance(args, dict) else args,
        "reason": payload.get("reason"),
    }
