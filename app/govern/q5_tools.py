"""Deterministic read-only Q5 observation tools with auditable events."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.govern.q5_context import Q5TrustedObservation
from app.govern.q5_environment import Q5ReadOnlyEnvironment
from app.govern.q5_tool_validator import Q5ValidatedToolCall
from app.schemas.q5_task import Q5ObservationTool


class Q5ToolStatus(StrEnum):
    ok = "ok"
    not_found = "not_found"
    timeout = "timeout"
    invalid = "invalid"


class Q5PolicyExceptionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_type: Literal["policy_exception"] = "policy_exception"
    resource_ref: str
    policy_ref: str
    status: Literal["active", "expired", "missing"]
    scope: str | None = None


class Q5ChangeStateObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_type: Literal["change_state"] = "change_state"
    change_ref: str
    status: Literal["planned", "in_progress", "completed", "unknown"]


class Q5IncidentImpactObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_type: Literal["incident_impact"] = "incident_impact"
    resource_ref: str
    status: Literal["none", "degraded", "outage", "unknown"]


Q5TypedObservation = (
    Q5PolicyExceptionObservation
    | Q5ChangeStateObservation
    | Q5IncidentImpactObservation
)


class Q5ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: Q5ObservationTool
    request_id: str
    status: Q5ToolStatus
    observation: Q5TypedObservation | None = None
    provenance: str
    untrusted_text: str | None = None

    def trusted_context_slice(self) -> Q5TrustedObservation:
        return Q5TrustedObservation(
            tool_name=self.tool_name,
            request_id=self.request_id,
            status=self.status.value,
            observation=(
                self.observation.model_dump(mode="json")
                if self.observation is not None
                else None
            ),
            provenance=self.provenance,
        )


class Q5ToolEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["q5_tool_call"] = "q5_tool_call"
    tool_name: Q5ObservationTool
    request_id: str
    request_args: dict[str, str]
    status: Q5ToolStatus
    observation: dict[str, Any] | None = None
    provenance: str
    untrusted_text: str | None = None
    latency_ms: float = Field(ge=0)
    read_only: Literal[True] = True


class Q5ToolExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result: Q5ToolResult
    event: Q5ToolEvent
    span_payload: dict[str, Any]


class Q5ToolExecutor:
    """Executes only prevalidated calls against a read-only environment snapshot."""

    def __init__(self, environment: Q5ReadOnlyEnvironment) -> None:
        self.environment = environment
        self._request_count = 0

    def execute(self, call: Q5ValidatedToolCall) -> Q5ToolExecution:
        self._request_count += 1
        request_id = f"q5-tool-{self._request_count:04d}"
        start_unix_ns = time.time_ns()
        start_perf_ns = time.perf_counter_ns()
        result = self._execute(call, request_id)
        end_perf_ns = time.perf_counter_ns()
        end_unix_ns = time.time_ns()
        latency_ms = max(0.0, (end_perf_ns - start_perf_ns) / 1_000_000)
        observation = (
            result.observation.model_dump(mode="json")
            if result.observation is not None
            else None
        )
        event = Q5ToolEvent(
            tool_name=call.tool,
            request_id=request_id,
            request_args=dict(call.args),
            status=result.status,
            observation=observation,
            provenance=result.provenance,
            untrusted_text=result.untrusted_text,
            latency_ms=latency_ms,
        )
        span = {
            "name": f"q5.tool.{call.tool.value}",
            "kind": "INTERNAL",
            "start_time_unix_nano": start_unix_ns,
            "end_time_unix_nano": end_unix_ns,
            "status": {"code": "OK" if result.status is Q5ToolStatus.ok else "ERROR"},
            "attributes": {
                "q5.tool.name": call.tool.value,
                "q5.tool.request_id": request_id,
                "q5.tool.status": result.status.value,
                "q5.tool.read_only": True,
                "q5.environment_ref": self.environment.environment_ref,
                "q5.environment_version": self.environment.state_version,
            },
        }
        return Q5ToolExecution(result=result, event=event, span_payload=span)

    def _execute(self, call: Q5ValidatedToolCall, request_id: str) -> Q5ToolResult:
        fault = self.environment.tool_fault(call.tool)
        if fault:
            status = str(fault.get("status", "invalid"))
            if status in {Q5ToolStatus.timeout.value, Q5ToolStatus.invalid.value}:
                return Q5ToolResult(
                    tool_name=call.tool,
                    request_id=request_id,
                    status=Q5ToolStatus(status),
                    observation=None,
                    provenance=self.environment.provenance,
                    untrusted_text=_optional_text(fault.get("untrusted_text")),
                )

        if call.tool is Q5ObservationTool.lookup_policy_exception:
            return self._lookup_policy_exception(call, request_id)
        if call.tool is Q5ObservationTool.inspect_change_state:
            return self._inspect_change_state(call, request_id)
        if call.tool is Q5ObservationTool.inspect_incident_impact:
            return self._inspect_incident_impact(call, request_id)
        return Q5ToolResult(
            tool_name=call.tool,
            request_id=request_id,
            status=Q5ToolStatus.invalid,
            observation=None,
            provenance=self.environment.provenance,
        )

    def _lookup_policy_exception(
        self,
        call: Q5ValidatedToolCall,
        request_id: str,
    ) -> Q5ToolResult:
        resource_ref = call.args["resource_ref"]
        policy_ref = call.args["policy_ref"]
        entry = self.environment.policy_exception(resource_ref, policy_ref)
        if entry is None:
            return self._result(
                call.tool,
                request_id,
                Q5ToolStatus.not_found,
                Q5PolicyExceptionObservation(
                    resource_ref=resource_ref,
                    policy_ref=policy_ref,
                    status="missing",
                ),
            )
        untrusted_text = _optional_text(entry.pop("untrusted_text", None))
        status = str(entry.get("status", "missing"))
        if status not in {"active", "expired", "missing"}:
            return self._result(
                call.tool,
                request_id,
                Q5ToolStatus.invalid,
                None,
                untrusted_text=untrusted_text,
            )
        return self._result(
            call.tool,
            request_id,
            Q5ToolStatus.ok,
            Q5PolicyExceptionObservation(
                resource_ref=resource_ref,
                policy_ref=policy_ref,
                status=status,
                scope=_optional_text(entry.get("scope")),
            ),
            untrusted_text=untrusted_text,
        )

    def _inspect_change_state(
        self,
        call: Q5ValidatedToolCall,
        request_id: str,
    ) -> Q5ToolResult:
        change_ref = call.args["change_ref"]
        entry = self.environment.change_state(change_ref)
        if entry is None:
            return self._result(
                call.tool,
                request_id,
                Q5ToolStatus.not_found,
                Q5ChangeStateObservation(change_ref=change_ref, status="unknown"),
            )
        untrusted_text = _optional_text(entry.pop("untrusted_text", None))
        status = str(entry.get("status", "unknown"))
        if status not in {"planned", "in_progress", "completed", "unknown"}:
            return self._result(
                call.tool,
                request_id,
                Q5ToolStatus.invalid,
                None,
                untrusted_text=untrusted_text,
            )
        return self._result(
            call.tool,
            request_id,
            Q5ToolStatus.ok,
            Q5ChangeStateObservation(change_ref=change_ref, status=status),
            untrusted_text=untrusted_text,
        )

    def _inspect_incident_impact(
        self,
        call: Q5ValidatedToolCall,
        request_id: str,
    ) -> Q5ToolResult:
        resource_ref = call.args["resource_ref"]
        entry = self.environment.incident_impact(resource_ref)
        if entry is None:
            return self._result(
                call.tool,
                request_id,
                Q5ToolStatus.not_found,
                Q5IncidentImpactObservation(resource_ref=resource_ref, status="unknown"),
            )
        untrusted_text = _optional_text(entry.pop("untrusted_text", None))
        status = str(entry.get("status", "unknown"))
        if status not in {"none", "degraded", "outage", "unknown"}:
            return self._result(
                call.tool,
                request_id,
                Q5ToolStatus.invalid,
                None,
                untrusted_text=untrusted_text,
            )
        return self._result(
            call.tool,
            request_id,
            Q5ToolStatus.ok,
            Q5IncidentImpactObservation(resource_ref=resource_ref, status=status),
            untrusted_text=untrusted_text,
        )

    def _result(
        self,
        tool: Q5ObservationTool,
        request_id: str,
        status: Q5ToolStatus,
        observation: Q5TypedObservation | None,
        *,
        untrusted_text: str | None = None,
    ) -> Q5ToolResult:
        return Q5ToolResult(
            tool_name=tool,
            request_id=request_id,
            status=status,
            observation=observation,
            provenance=self.environment.provenance,
            untrusted_text=untrusted_text,
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
