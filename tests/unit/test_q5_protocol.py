from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.eval.q5_protocol import (
    Q5ProtocolVersion,
    resolve_q5_artifact_protocol,
)
from app.eval.q5_protocol_v1 import Q5StructuredProposalV1
from app.govern.q5_context import Q5StructuredProposal


def test_q5_v1_proposal_semantics_remain_frozen() -> None:
    payload = {
        "kind": "observe",
        "tool": "lookup_policy_exception",
        "args": {},
        "action": None,
        "evidence_chunk_ids": ["chunk-v1"],
        "reason_code": "short_enum",
        "reason_summary": "Inspect the runtime state.",
    }

    parsed = Q5StructuredProposalV1.model_validate(payload)

    assert parsed.args == {}
    assert parsed.reason_code == "short_enum"
    with pytest.raises(ValidationError, match="non-empty tool args"):
        Q5StructuredProposal.model_validate(payload)


@pytest.mark.parametrize(
    ("schema", "prompt", "version"),
    [
        ("q5-run-manifest-v1", "q5-structured-policy-v1", "v1"),
        ("q5-run-manifest-v2", "q5-structured-policy-v2", "v2"),
        ("q5-run-manifest-v3", "q5-structured-policy-v3", "v3"),
        ("q5-run-manifest-v4", "q5-structured-policy-v4", "v4"),
    ],
)
def test_q5_protocol_dispatch_requires_matching_run_and_prompt_versions(
    schema: str,
    prompt: str,
    version: str,
) -> None:
    resolved = resolve_q5_artifact_protocol(
        {"schema_version": schema, "prompt": {"version": prompt}}
    )

    assert resolved.version is Q5ProtocolVersion(version)


def test_q5_protocol_dispatch_rejects_cross_version_prompt() -> None:
    with pytest.raises(ValueError, match="manifest/prompt protocol mismatch"):
        resolve_q5_artifact_protocol(
            {
                "schema_version": "q5-run-manifest-v1",
                "prompt": {"version": "q5-structured-policy-v2"},
            }
        )
