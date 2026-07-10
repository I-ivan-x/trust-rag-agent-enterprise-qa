"""Read-only deterministic environment surface for Q5 observation tools."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.schemas.q5_task import Q5EnvironmentState, Q5ObservationTool


@dataclass(frozen=True)
class Q5ReadOnlyEnvironment:
    """Immutable-by-interface snapshot shared by every Q5 policy arm."""

    _state: Q5EnvironmentState
    state_version: str

    @classmethod
    def from_state(cls, state: Q5EnvironmentState) -> Q5ReadOnlyEnvironment:
        canonical = json.dumps(
            state.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        version = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        return cls(_state=state.model_copy(deep=True), state_version=version)

    @property
    def environment_ref(self) -> str:
        return self._state.environment_ref

    @property
    def provenance(self) -> str:
        return f"q5-env:{self.state_version}"

    def policy_exception(self, resource_ref: str, policy_ref: str) -> dict[str, Any] | None:
        keys = (
            f"{resource_ref}|{policy_ref}",
            f"{resource_ref}::{policy_ref}",
        )
        for key in keys:
            if key in self._state.policy_exceptions:
                return deepcopy(self._state.policy_exceptions[key])
        nested = self._state.policy_exceptions.get(resource_ref)
        if isinstance(nested, dict) and isinstance(nested.get(policy_ref), dict):
            return deepcopy(nested[policy_ref])
        return None

    def change_state(self, change_ref: str) -> dict[str, Any] | None:
        value = self._state.change_states.get(change_ref)
        return deepcopy(value) if value is not None else None

    def incident_impact(self, resource_ref: str) -> dict[str, Any] | None:
        value = self._state.incident_impacts.get(resource_ref)
        return deepcopy(value) if value is not None else None

    def tool_fault(self, tool: Q5ObservationTool) -> dict[str, Any] | None:
        if not self._state.tool_faults:
            return None
        value = self._state.tool_faults.get(tool.value)
        return deepcopy(value) if value is not None else None
