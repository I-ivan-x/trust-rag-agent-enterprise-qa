"""Deterministic runtime-only Q5 mock policy used by synthetic harness tests."""

from __future__ import annotations

import json
from typing import Any


class Q5DeterministicMockPolicyModel:
    """Choose from runtime context only; this model has no gold or stratum input."""

    provider = "deterministic_mock"
    model_name = "q5-runtime-policy-v1"
    mock_used = True

    def generate(self, prompt: str) -> str:
        context = _runtime_context(prompt)
        conditions = {
            str(value).strip().lower() for value in context.get("conditions") or []
        }
        observations = list(context.get("observations") or [])
        available_tools = set(context.get("available_tools") or [])
        legal_actions = set(context.get("legal_terminal_actions") or [])
        evidence_ids = [
            str(item["chunk_id"])
            for item in context.get("authorized_evidence") or []
            if isinstance(item, dict) and item.get("chunk_id")
        ]

        if (
            "permission_blocked" in conditions
            or "insufficient_evidence" in conditions
            or context.get("evidence_decision") == "insufficient"
        ):
            return _terminal(
                "escalate_to_human",
                evidence_ids,
                "runtime_policy_block",
            )

        if conditions & {"config_violation", "policy_violation"}:
            observation = _last_observation(observations, "lookup_policy_exception")
            if observation is None and "lookup_policy_exception" in available_tools:
                return _observe(
                    "lookup_policy_exception",
                    {
                        "resource_ref": _first_ref(context, "resource:"),
                        "policy_ref": _first_ref(context, "policy:"),
                    },
                    evidence_ids,
                    "inspect_policy_exception",
                )
            status = _observation_status(observation)
            action = (
                "escalate_to_human"
                if status == "active"
                else "open_remediation_ticket"
            )
            return _terminal(
                _legal_or_escalate(action, legal_actions),
                evidence_ids,
                "policy_state_applied",
            )

        if conditions & {"stale_procedure", "missing_prereq"}:
            observation = _last_observation(observations, "inspect_change_state")
            change_ref = _first_ref(context, "change:")
            if (
                observation is None
                and change_ref is not None
                and "inspect_change_state" in available_tools
            ):
                return _observe(
                    "inspect_change_state",
                    {"change_ref": change_ref},
                    evidence_ids,
                    "inspect_change_state",
                )
            action = "flag_stale" if "stale_procedure" in conditions else "open_remediation_ticket"
            return _terminal(
                _legal_or_escalate(action, legal_actions),
                evidence_ids,
                "stale_state_applied",
            )

        if "active_active_conflict" in conditions:
            observation = _last_observation(observations, "inspect_incident_impact")
            if observation is None and "inspect_incident_impact" in available_tools:
                return _observe(
                    "inspect_incident_impact",
                    {"resource_ref": _first_ref(context, "resource:")},
                    evidence_ids,
                    "inspect_incident_impact",
                )
            action = (
                "send_alert"
                if _observation_status(observation) in {"degraded", "outage"}
                else "escalate_to_human"
            )
            return _terminal(
                _legal_or_escalate(action, legal_actions),
                evidence_ids,
                "incident_state_applied",
            )

        return _terminal(
            _legal_or_escalate("no_op", legal_actions),
            evidence_ids,
            "no_runtime_action_needed",
        )


def _runtime_context(prompt: str) -> dict[str, Any]:
    marker = "RUNTIME_CONTEXT:\n"
    if marker not in prompt:
        raise ValueError("Q5 prompt is missing RUNTIME_CONTEXT")
    payload = json.loads(prompt.split(marker, 1)[1])
    if not isinstance(payload, dict):
        raise ValueError("Q5 runtime context must be an object")
    return payload


def _last_observation(
    observations: list[Any],
    tool_name: str,
) -> dict[str, Any] | None:
    for item in reversed(observations):
        if isinstance(item, dict) and item.get("tool_name") == tool_name:
            return item
    return None


def _observation_status(observation: dict[str, Any] | None) -> str:
    if observation is None:
        return "unknown"
    if observation.get("status") in {"timeout", "invalid"}:
        return str(observation["status"])
    payload = observation.get("observation")
    return str(payload.get("status", "unknown")) if isinstance(payload, dict) else "unknown"


def _first_ref(context: dict[str, Any], prefix: str) -> str | None:
    for value in context.get("resource_refs") or []:
        if isinstance(value, str) and value.startswith(prefix):
            return value
    return None


def _observe(
    tool: str,
    args: dict[str, str | None],
    evidence_ids: list[str],
    reason_code: str,
) -> str:
    return json.dumps(
        {
            "kind": "observe",
            "tool": tool,
            "args": args,
            "action": None,
            "evidence_chunk_ids": evidence_ids,
            "reason_code": reason_code,
            "reason_summary": (
                "A typed runtime observation is required before the terminal decision."
            ),
        },
        sort_keys=True,
    )


def _terminal(action: str, evidence_ids: list[str], reason_code: str) -> str:
    return json.dumps(
        {
            "kind": "terminal",
            "tool": None,
            "args": {},
            "action": action,
            "evidence_chunk_ids": evidence_ids,
            "reason_code": reason_code,
            "reason_summary": "The typed runtime state supports this terminal decision.",
        },
        sort_keys=True,
    )


def _legal_or_escalate(action: str, legal_actions: set[str]) -> str:
    return action if action in legal_actions else "escalate_to_human"
