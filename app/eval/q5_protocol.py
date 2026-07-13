"""Explicit Q5 artifact protocol identities and coherent-version dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Q5ProtocolVersion(StrEnum):
    v1 = "v1"
    v2 = "v2"
    v3 = "v3"
    v4 = "v4"


@dataclass(frozen=True)
class Q5ProtocolSpec:
    version: Q5ProtocolVersion
    run_manifest_schema: str
    graded_manifest_schema: str
    metrics_schema: str
    gates_schema: str
    prompt_version: str


Q5_PROTOCOL_V1 = Q5ProtocolSpec(
    version=Q5ProtocolVersion.v1,
    run_manifest_schema="q5-run-manifest-v1",
    graded_manifest_schema="q5-graded-manifest-v1",
    metrics_schema="q5-metrics-v1",
    gates_schema="q5-gates-v1",
    prompt_version="q5-structured-policy-v1",
)
Q5_PROTOCOL_V2 = Q5ProtocolSpec(
    version=Q5ProtocolVersion.v2,
    run_manifest_schema="q5-run-manifest-v2",
    graded_manifest_schema="q5-graded-manifest-v2",
    metrics_schema="q5-metrics-v2",
    gates_schema="q5-gates-v2",
    prompt_version="q5-structured-policy-v2",
)
Q5_PROTOCOL_V3 = Q5ProtocolSpec(
    version=Q5ProtocolVersion.v3,
    run_manifest_schema="q5-run-manifest-v3",
    graded_manifest_schema="q5-graded-manifest-v3",
    metrics_schema="q5-metrics-v3",
    gates_schema="q5-gates-v3",
    prompt_version="q5-structured-policy-v3",
)
Q5_PROTOCOL_V4 = Q5ProtocolSpec(
    version=Q5ProtocolVersion.v4,
    run_manifest_schema="q5-run-manifest-v4",
    graded_manifest_schema="q5-graded-manifest-v4",
    metrics_schema="q5-metrics-v4",
    gates_schema="q5-gates-v4",
    prompt_version="q5-structured-policy-v4",
)
_PROTOCOL_BY_RUN_SCHEMA = {
    Q5_PROTOCOL_V1.run_manifest_schema: Q5_PROTOCOL_V1,
    Q5_PROTOCOL_V2.run_manifest_schema: Q5_PROTOCOL_V2,
    Q5_PROTOCOL_V3.run_manifest_schema: Q5_PROTOCOL_V3,
    Q5_PROTOCOL_V4.run_manifest_schema: Q5_PROTOCOL_V4,
}


def resolve_q5_artifact_protocol(
    raw_manifest: Mapping[str, Any],
    *,
    graded_manifest: Mapping[str, Any] | None = None,
    summary: Mapping[str, Any] | None = None,
    gates: Mapping[str, Any] | None = None,
) -> Q5ProtocolSpec:
    """Resolve one coherent protocol; mixed-version artifact sets fail closed."""

    run_schema = raw_manifest.get("schema_version")
    protocol = _PROTOCOL_BY_RUN_SCHEMA.get(str(run_schema))
    if protocol is None:
        raise ValueError(f"unsupported Q5 run manifest schema: {run_schema}")
    prompt = raw_manifest.get("prompt")
    prompt_version = prompt.get("version") if isinstance(prompt, Mapping) else None
    if prompt_version != protocol.prompt_version:
        raise ValueError(
            "Q5 run manifest/prompt protocol mismatch: "
            f"schema={run_schema}, prompt={prompt_version}"
        )
    expected = (
        ("graded manifest", graded_manifest, protocol.graded_manifest_schema),
        ("metrics", summary, protocol.metrics_schema),
        ("gates", gates, protocol.gates_schema),
    )
    for label, artifact, expected_schema in expected:
        if artifact is not None and artifact.get("schema_version") != expected_schema:
            raise ValueError(
                "Q5 artifact protocol mismatch: "
                f"run={protocol.version.value}, {label}="
                f"{artifact.get('schema_version')}"
            )
    return protocol
