"""Fail-closed compiler frozen before parser-uncovered-dev authoring."""

from __future__ import annotations

from app.eval.q5_frontier_compiler_v3 import compile_policy_ir_v3
from app.schemas.q5_frontier import CanonicalPolicyIR, FrontierDisposition
from app.schemas.q5_frontier_v3 import FrontierRuntimePayloadV3
from app.schemas.q5_frontier_v4 import (
    FrontierCompilerResultV4,
    FrontierRuntimePayloadV4,
    validate_v4_policy_ir,
)

RESOURCE_OBSERVATION_FAMILY = {
    "incident": "inspect_incident_state",
    "change": "inspect_change_state",
    "access": "inspect_access_scope",
    "retention": "inspect_retention_state",
}


def compile_policy_ir_v4(
    policy_ir: CanonicalPolicyIR,
    runtime_payload: FrontierRuntimePayloadV4,
) -> FrontierCompilerResultV4:
    validate_v4_policy_ir(policy_ir)
    observation = runtime_payload.trusted_observation
    family_matches = (
        RESOURCE_OBSERVATION_FAMILY[policy_ir.scope.resource_type.value]
        == policy_ir.evidence_requirements.observation_type
        == observation.observation_type.value
    )
    if not family_matches:
        return FrontierCompilerResultV4(
            disposition=FrontierDisposition.human_review,
            resource_observation_family_matches=False,
            scope_applicable=False,
            temporal_applicable=False,
            authorized=observation.authorization.authorized,
            observation_completed=observation.success,
            exception_matched=False,
            precedence_applied="safety_guard",
        )
    compatible = FrontierRuntimePayloadV3(
        runtime_ref=runtime_payload.runtime_ref.replace(
            "parser-uncovered-dev-resource", "frontier-v3-resource"
        ),
        policy_text=runtime_payload.policy_text,
        query=runtime_payload.query,
        legal_dispositions=runtime_payload.legal_dispositions,
        trusted_observation=observation,
    )
    result = compile_policy_ir_v3(policy_ir, compatible)
    return FrontierCompilerResultV4(
        disposition=result.disposition,
        resource_observation_family_matches=True,
        scope_applicable=result.scope_applicable,
        temporal_applicable=result.temporal_applicable,
        authorized=result.authorized,
        observation_completed=result.observation_completed,
        exception_matched=result.exception_matched,
        precedence_applied=result.precedence_applied,
    )
