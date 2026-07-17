"""Preregistered contracts for the Q5 parser-uncovered development frontier."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.q5_frontier import CanonicalPolicyIR, FrontierDisposition
from app.schemas.q5_frontier_v2 import FrontierTrustedObservation


class FrontierRuntimePayloadV4(BaseModel):
    """Execution-visible payload; authoring labels and sealed IR are forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_ref: str = Field(pattern=r"^parser-uncovered-dev-resource:r[0-9]{3}$")
    policy_text: str = Field(min_length=1)
    query: str = Field(min_length=1)
    legal_dispositions: list[FrontierDisposition] = Field(min_length=1)
    trusted_observation: FrontierTrustedObservation

    @model_validator(mode="after")
    def _closed_surface(self) -> FrontierRuntimePayloadV4:
        if len(self.legal_dispositions) != len(set(self.legal_dispositions)):
            raise ValueError("legal dispositions must be unique")
        if FrontierDisposition.human_review not in self.legal_dispositions:
            raise ValueError("human_review must remain legal")
        return self


class FrontierCompilerResultV4(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: FrontierDisposition
    resource_observation_family_matches: bool
    requirement_flags_enforced: Literal[True] = True
    scope_applicable: bool
    temporal_applicable: bool
    authorized: bool
    observation_completed: bool
    exception_matched: bool
    precedence_applied: Literal[
        "safety_guard",
        "ambiguity_guard",
        "base_only",
        "exception_overrides",
        "deny_overrides",
    ]


class FrontierParserOutcomeV4(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["complete", "abstain", "ambiguous", "unsafe"]
    reason: str
    parser_name: Literal[
        "structured_parser",
        "boundary_b_parser",
        "compositional_challenger",
        "alias_condition_normalizer",
        "best_of_deterministic_selector",
    ]
    policy_ir: CanonicalPolicyIR | None = None

    @model_validator(mode="after")
    def _complete_has_ir(self) -> FrontierParserOutcomeV4:
        if (self.status == "complete") != (self.policy_ir is not None):
            raise ValueError("only complete parser outcomes carry Policy IR")
        return self


def validate_v4_policy_ir(policy_ir: CanonicalPolicyIR) -> CanonicalPolicyIR:
    """Enforce the four frozen evidence/safety requirements.

    The two evidence flags mean that compilation requires a host-authorized
    evidence chunk and a completed typed observation.  The two terminal flags
    repeat those requirements at the terminal boundary.  V4 fixes all four to
    true; false is not a configurable policy option.
    """

    flags = (
        policy_ir.evidence_requirements.authorized_chunk_required,
        policy_ir.evidence_requirements.successful_observation_required,
        policy_ir.terminal_safety.require_authorized_evidence,
        policy_ir.terminal_safety.require_successful_observation,
    )
    if flags != (True, True, True, True):
        raise ValueError("all four v4 evidence and terminal requirement flags must be true")
    return policy_ir


def compact_policy_ir_prompt_contract_v4() -> dict[str, Any]:
    """Single typed prompt-output contract; no examples or authored answers."""

    schema = CanonicalPolicyIR.model_json_schema()

    def compact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: compact(item)
                for key, item in sorted(value.items())
                if key not in {"title", "description", "default", "examples"}
            }
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    return {
        "schema_version": "q5-frontier-prompt-contract-v4",
        "input_fields": [
            "policy_text",
            "query",
            "legal_dispositions",
            "trusted_observation",
        ],
        "forbidden_fields": ["gold", "topology", "case_id", "expected_action"],
        "output_schema": compact(schema),
        "requirement_flags": {
            "authorized_chunk_required": {"const": True},
            "successful_observation_required": {"const": True},
            "require_authorized_evidence": {"const": True},
            "require_successful_observation": {"const": True},
        },
    }
