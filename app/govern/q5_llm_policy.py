"""Strict Q5 LLM policy adapter with no implicit rule fallback."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from app.govern.q5_context import (
    Q5DecisionContext,
    build_q5_prompt,
    parse_q5_structured_proposal,
)
from app.govern.q5_policy import Q5PolicyModel, Q5PolicyStep


class Q5LLMAgentPolicy:
    policy_source = "llm"

    def __init__(self, model: Q5PolicyModel | None) -> None:
        self.model = model

    def decide(self, context: Q5DecisionContext) -> Q5PolicyStep:
        if self.model is None:
            return Q5PolicyStep(
                policy_source="llm",
                parse_status="model_error",
                error_reason="model_not_configured",
                llm_called=False,
            )
        prompt = build_q5_prompt(context)
        try:
            raw = self.model.generate(prompt)
        except Exception as exc:
            return Q5PolicyStep(
                policy_source="llm",
                parse_status="model_error",
                error_reason=f"model_error:{type(exc).__name__}",
                llm_called=True,
            )
        raw_hash = _payload_hash(raw)
        try:
            proposal = parse_q5_structured_proposal(raw)
        except (json.JSONDecodeError, TypeError):
            return Q5PolicyStep(
                policy_source="llm",
                parse_status="parse_error",
                error_reason="structured_proposal_parse_error",
                raw_payload_sha256=raw_hash,
                llm_called=True,
            )
        except ValueError:
            return Q5PolicyStep(
                policy_source="llm",
                parse_status="parse_error",
                error_reason=_schema_error_reason(raw),
                raw_payload_sha256=raw_hash,
                llm_called=True,
            )
        return Q5PolicyStep(
            proposal=proposal,
            policy_source="llm",
            parse_status="accepted",
            raw_payload_sha256=raw_hash,
            llm_called=True,
        )


def _payload_hash(payload: Any) -> str:
    if isinstance(payload, Mapping):
        raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)
    else:
        raw = str(payload)
    return hashlib.sha256(raw.encode()).hexdigest()


def _schema_error_reason(payload: Any) -> str:
    try:
        parsed = json.loads(payload) if isinstance(payload, str) else dict(payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        return "structured_proposal_schema_invalid"
    if isinstance(parsed, dict) and parsed.get("kind") == "observe":
        return "tool_schema_invalid"
    return "structured_proposal_schema_invalid"
