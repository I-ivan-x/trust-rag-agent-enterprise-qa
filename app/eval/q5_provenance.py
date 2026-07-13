"""Trusted Q5 model identity and artifact provenance verification."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.eval.q5_dataset import load_q5_gold
from app.eval.q5_metrics import (
    Q5_ALWAYS_HUMAN_REVIEW_CONTROL,
    Q5_ESCALATE_EVERYTHING_CONTROL,
    compute_q5_metrics,
    evaluate_q5_gates,
)
from app.eval.q5_mock import Q5DeterministicMockPolicyModel
from app.eval.q5_protocol import (
    Q5ProtocolVersion,
    resolve_q5_artifact_protocol,
)
from app.eval.q5_protocol_v1 import (
    compute_q5_metrics_v1,
    evaluate_q5_gates_v1,
    grade_q5_artifact_rows_v1,
    render_q5_report_v1,
)
from app.eval.q5_protocol_v2 import (
    compute_q5_metrics_v2,
    evaluate_q5_gates_v2,
    grade_q5_artifact_rows_v2,
    render_q5_report_v2,
)
from app.eval.q5_protocol_v3 import (
    compute_q5_metrics_v3,
    evaluate_q5_gates_v3,
    render_q5_report_v3,
)
from app.eval.q5_report import render_q5_report
from app.llm.llm_client import (
    DeepSeekLLMClient,
    OpenAICompatibleLLMClient,
    XiaomiLLMClient,
)
from app.llm.mock_llm import MockLLMClient

Q5_RAW_ARTIFACT_FILES = frozenset(
    {
        "environment_before.json",
        "environment_after.json",
        "tool_events.jsonl",
        "policy_events.jsonl",
        "terminal_events.jsonl",
        "trajectory.jsonl",
        "otel_spans.jsonl",
        "results.jsonl",
        "manifest.json",
        "hashes.json",
    }
)
Q5_GRADED_ARTIFACT_FILES = frozenset(
    {
        "graded_rows.jsonl",
        "analytic_controls.jsonl",
        "summary.json",
        "gates.json",
        "report.md",
        "graded_manifest.json",
        "graded_hashes.json",
    }
)


class Q5ModelIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    instance_type: str = Field(min_length=1)
    identity_kind: Literal["trusted_real_client", "known_mock", "untrusted_adapter"]
    mock_instance: bool
    trusted_real_client: bool
    base_url_host: str | None = None
    identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_attested_identity(self) -> Q5ModelIdentity:
        trusted_types = {
            "app.llm.llm_client.OpenAICompatibleLLMClient": {
                "openai",
                "openai_compatible",
            },
            "app.llm.llm_client.DeepSeekLLMClient": {"deepseek"},
            "app.llm.llm_client.XiaomiLLMClient": {"xiaomi"},
        }
        if self.identity_kind == "trusted_real_client":
            allowed_providers = trusted_types.get(self.instance_type)
            if (
                not self.trusted_real_client
                or self.mock_instance
                or not self.base_url_host
                or allowed_providers is None
                or self.provider not in allowed_providers
            ):
                raise ValueError("invalid Q5 trusted-real model attestation")
        elif (
            self.trusted_real_client
            or not self.mock_instance
            or self.base_url_host is not None
        ):
            raise ValueError("invalid Q5 mock/untrusted model attestation")
        canonical = self.model_dump(mode="json", exclude={"identity_sha256"})
        if self.identity_sha256 != q5_hash_payload(canonical):
            raise ValueError("Q5 model identity provenance hash mismatch")
        return self


class Q5VerifiedRunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_dir: Path
    run_id: str
    model_role: Literal["primary", "confirmatory"]
    raw_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    graded_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gates_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_identities: list[Q5ModelIdentity] = Field(min_length=1)
    provider_model_pairs: list[str] = Field(min_length=1)
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: str
    mock_used: bool
    real_run: bool
    protocol_version: Literal["v1", "v2", "v3", "v4"]


def canonical_q5_model_family(identity: Q5ModelIdentity) -> str:
    """Resolve one family from model, type, provider, and endpoint evidence."""

    evidence = _q5_model_family_evidence(identity)
    families = {
        family
        for source_families in evidence.values()
        for family in source_families
    }
    if len(families) > 1:
        detail = ", ".join(
            f"{source}={sorted(source_families)}"
            for source, source_families in sorted(evidence.items())
            if source_families
        )
        raise ValueError(f"conflicting Q5 model-family evidence: {detail}")
    return next(iter(families), "unresolved")


def q5_model_deployment_fingerprint(
    identity: Q5ModelIdentity,
) -> tuple[str, str, str]:
    """Provider-independent deployment key used to reject alias relabeling."""

    return (
        identity.instance_type.strip().lower(),
        _normalized_endpoint_host(identity.base_url_host),
        identity.model_name.strip().lower(),
    )


def validate_q5_cross_family_identities(
    primary: list[Q5ModelIdentity],
    confirmatory: list[Q5ModelIdentity],
) -> None:
    """Require one internally consistent and genuinely distinct family per role."""

    if not primary or not confirmatory:
        raise ValueError("Q5 dual-model runs require complete model identities")
    primary_families = {canonical_q5_model_family(identity) for identity in primary}
    confirmatory_families = {
        canonical_q5_model_family(identity) for identity in confirmatory
    }
    if len(primary_families) != 1 or len(confirmatory_families) != 1:
        raise ValueError("each Q5 model role must resolve to exactly one model family")
    primary_deployments = {
        q5_model_deployment_fingerprint(identity) for identity in primary
    }
    confirmatory_deployments = {
        q5_model_deployment_fingerprint(identity) for identity in confirmatory
    }
    if len(primary_deployments) != 1 or len(confirmatory_deployments) != 1:
        raise ValueError("each Q5 model role must resolve to exactly one deployment")
    if primary_deployments & confirmatory_deployments:
        raise ValueError(
            "Q5 primary and confirmatory identities alias the same model deployment"
        )
    if "unresolved" in primary_families | confirmatory_families:
        raise ValueError("Q5 cross-family confirmation has insufficient family evidence")
    if primary_families & confirmatory_families:
        raise ValueError(
            "Q5 primary and confirmatory runs must use distinct canonical model families"
        )


def _q5_model_family_evidence(
    identity: Q5ModelIdentity,
) -> dict[str, set[str]]:
    provider = identity.provider.lower().replace("-", "_").strip()
    instance_type = identity.instance_type.strip()
    family_host = _normalized_endpoint_host(identity.base_url_host).partition(":")[0]
    provider_families = {
        "deepseek": "deepseek",
        "xiaomi": "xiaomi",
        "mimo": "xiaomi",
        "qwen": "qwen",
        "dashscope": "qwen",
        "alibaba": "qwen",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "google": "google",
        "gemini": "google",
        "mistral": "mistral",
        "xai": "xai",
        "grok": "xai",
        "meta": "meta",
        "llama": "meta",
        "cohere": "cohere",
    }
    provider_family = provider_families.get(provider)
    instance_family = None
    if instance_type.endswith(".DeepSeekLLMClient"):
        instance_family = "deepseek"
    elif instance_type.endswith(".XiaomiLLMClient"):
        instance_family = "xiaomi"
    endpoint_family = _q5_endpoint_family(family_host)
    return {
        "model_name": _q5_model_name_families(identity.model_name),
        "instance_type": {instance_family} if instance_family else set(),
        "provider": {provider_family} if provider_family else set(),
        "endpoint_host": {endpoint_family} if endpoint_family else set(),
    }


def _q5_model_name_families(model_name: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", model_name.lower()))
    families: set[str] = set()
    if any(token.startswith("deepseek") for token in tokens):
        families.add("deepseek")
    if any(token.startswith(("mimo", "xiaomi")) for token in tokens):
        families.add("xiaomi")
    if any(token.startswith(("qwen", "qwq")) for token in tokens):
        families.add("qwen")
    if any(
        token.startswith(("gpt", "chatgpt")) or token in {"o1", "o3", "o4"}
        for token in tokens
    ):
        families.add("openai")
    if any(token.startswith("claude") for token in tokens):
        families.add("anthropic")
    if any(token.startswith("gemini") for token in tokens):
        families.add("google")
    if any(token.startswith("llama") for token in tokens):
        families.add("meta")
    if any(
        token.startswith(("mistral", "mixtral", "codestral")) for token in tokens
    ):
        families.add("mistral")
    if any(token.startswith("grok") for token in tokens):
        families.add("xai")
    if any(token.startswith("cohere") for token in tokens):
        families.add("cohere")
    return families


def _q5_endpoint_family(host: str) -> str | None:
    endpoint_suffixes = {
        "deepseek": ("deepseek.com",),
        "openai": ("api.openai.com",),
        "qwen": ("dashscope.aliyuncs.com",),
        "anthropic": ("api.anthropic.com",),
        "google": ("generativelanguage.googleapis.com",),
        "mistral": ("api.mistral.ai",),
        "xai": ("api.x.ai",),
        "cohere": ("api.cohere.com",),
    }
    for family, suffixes in endpoint_suffixes.items():
        if any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes):
            return family
    return None


def derive_q5_model_identity(model: Any) -> Q5ModelIdentity:
    """Derive identity from concrete instance type, never caller-supplied run flags."""

    instance_type = f"{type(model).__module__}.{type(model).__qualname__}"
    if type(model) in {
        OpenAICompatibleLLMClient,
        DeepSeekLLMClient,
        XiaomiLLMClient,
    }:
        _validate_real_client_instance(model)
        metadata = model.provider_metadata()
        provider = str(metadata.get("llm_provider") or model.provider)
        model_name = str(metadata.get("llm_model_name") or model.model_name)
        kind: Literal[
            "trusted_real_client", "known_mock", "untrusted_adapter"
        ] = "trusted_real_client"
        mock_instance = False
        trusted_real = True
        base_url_host = model.base_url_host
    elif isinstance(model, (Q5DeterministicMockPolicyModel, MockLLMClient)):
        provider = str(getattr(model, "provider", "deterministic_mock"))
        model_name = str(
            getattr(model, "model_name", type(model).__name__)
        )
        kind = "known_mock"
        mock_instance = True
        trusted_real = False
        base_url_host = None
    else:
        # Unknown adapters are fail-closed as mock/untrusted even if they expose
        # attributes claiming to be a real provider.
        provider = str(getattr(model, "provider", "untrusted_adapter"))
        model_name = str(getattr(model, "model_name", type(model).__name__))
        kind = "untrusted_adapter"
        mock_instance = True
        trusted_real = False
        base_url_host = None

    identity_payload = {
        "provider": provider,
        "model_name": model_name,
        "instance_type": instance_type,
        "identity_kind": kind,
        "mock_instance": mock_instance,
        "trusted_real_client": trusted_real,
        "base_url_host": base_url_host,
    }
    return Q5ModelIdentity(
        **identity_payload,
        identity_sha256=q5_hash_payload(identity_payload),
    )


def verify_q5_raw_artifact_closure(run_dir: Path | str) -> dict[str, Any]:
    root = Path(run_dir)
    actual_files = {path.name for path in root.iterdir()}
    missing = sorted(Q5_RAW_ARTIFACT_FILES - actual_files)
    extra = sorted(actual_files - Q5_RAW_ARTIFACT_FILES)
    if missing or extra:
        raise ValueError(f"Q5 raw artifact closure mismatch: missing={missing}, extra={extra}")
    hashes = q5_read_json(root / "hashes.json")
    expected_hash_names = Q5_RAW_ARTIFACT_FILES - {"hashes.json"}
    _verify_hash_mapping(root, hashes, expected_names=expected_hash_names)
    manifest = q5_read_json(root / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("Q5 manifest must be an object")
    return manifest


def verify_q5_graded_run(
    run_dir: Path | str,
    gold_path: Path | str,
) -> Q5VerifiedRunManifest:
    root = Path(run_dir)
    actual_files = {path.name for path in root.iterdir()}
    expected = Q5_RAW_ARTIFACT_FILES | Q5_GRADED_ARTIFACT_FILES
    missing = sorted(expected - actual_files)
    extra = sorted(actual_files - expected)
    if missing or extra:
        raise ValueError(
            f"Q5 graded artifact closure mismatch: missing={missing}, extra={extra}"
        )
    raw_manifest = q5_read_json(root / "manifest.json")
    raw_hashes = q5_read_json(root / "hashes.json")
    _verify_hash_mapping(
        root,
        raw_hashes,
        expected_names=Q5_RAW_ARTIFACT_FILES - {"hashes.json"},
    )
    from app.eval.q5_runner import grade_q5_artifact_rows, verify_q5_raw_trial_matrix

    graded_hashes = q5_read_json(root / "graded_hashes.json")
    _verify_hash_mapping(
        root,
        graded_hashes,
        expected_names=Q5_GRADED_ARTIFACT_FILES - {"graded_hashes.json"},
    )
    graded_manifest = q5_read_json(root / "graded_manifest.json")
    summary = q5_read_json(root / "summary.json")
    gates = q5_read_json(root / "gates.json")
    protocol = resolve_q5_artifact_protocol(
        raw_manifest,
        graded_manifest=graded_manifest,
        summary=summary,
        gates=gates,
    )
    raw_artifacts = verify_q5_raw_trial_matrix(root, manifest=raw_manifest)
    if graded_manifest.get("raw_manifest_sha256") != q5_sha256_file(
        root / "manifest.json"
    ):
        raise ValueError("Q5 graded manifest raw-manifest provenance mismatch")
    if graded_manifest.get("run_id") != raw_manifest.get("run_id"):
        raise ValueError("Q5 graded manifest run_id provenance mismatch")
    graded_dataset_hashes = graded_manifest.get("dataset_hashes")
    expected_dataset_hashes = {
        **(raw_manifest.get("dataset_hashes") or {}),
        "gold": (
            graded_dataset_hashes.get("gold")
            if isinstance(graded_dataset_hashes, dict)
            else None
        ),
    }
    if (
        not isinstance(graded_dataset_hashes, dict)
        or graded_dataset_hashes != expected_dataset_hashes
        or not isinstance(graded_dataset_hashes.get("gold"), str)
        or len(graded_dataset_hashes["gold"]) != 64
        or any(character not in "0123456789abcdef" for character in graded_dataset_hashes["gold"])
    ):
        raise ValueError("Q5 graded dataset hash provenance mismatch")
    sealed_gold_path = Path(gold_path)
    sealed_gold_sha256 = q5_sha256_file(sealed_gold_path)
    if graded_dataset_hashes["gold"] != sealed_gold_sha256:
        raise ValueError("Q5 sealed gold hash mismatch")
    sealed_gold = load_q5_gold(sealed_gold_path)
    graded_rows = q5_read_jsonl(root / "graded_rows.jsonl")
    analytic_rows = q5_read_jsonl(root / "analytic_controls.jsonl")
    if graded_manifest.get("graded_row_count") != len(graded_rows):
        raise ValueError("Q5 graded manifest row count mismatch")
    if graded_manifest.get("analytic_control_row_count") != len(analytic_rows):
        raise ValueError("Q5 analytic-control row count mismatch")
    if protocol.version is Q5ProtocolVersion.v1:
        expected_grading = grade_q5_artifact_rows_v1(
            manifest=raw_manifest,
            raw_artifacts=raw_artifacts,
            gold=sealed_gold,
        )
    elif protocol.version is Q5ProtocolVersion.v2:
        expected_grading = grade_q5_artifact_rows_v2(
            manifest=raw_manifest,
            raw_artifacts=raw_artifacts,
            gold=sealed_gold,
        )
    else:
        expected_grading = grade_q5_artifact_rows(
            manifest=raw_manifest,
            raw_artifacts=raw_artifacts,
            gold=sealed_gold,
        )
    if graded_rows != expected_grading.graded_rows:
        raise ValueError("Q5 graded rows do not match sealed-gold regrading")
    if analytic_rows != expected_grading.analytic_control_rows:
        raise ValueError("Q5 analytic controls do not match sealed-gold regrading")
    raw_by_trial = {
        _trial_tuple(row): row for row in raw_artifacts["results.jsonl"]
    }
    graded_by_trial: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in graded_rows:
        key = _trial_tuple(row)
        if key in graded_by_trial:
            raise ValueError(f"duplicate Q5 graded trial row: {key}")
        graded_by_trial[key] = row
    if set(graded_by_trial) != set(raw_by_trial):
        raise ValueError("Q5 graded/raw trial-key matrix mismatch")
    for key, raw in raw_by_trial.items():
        if any(graded_by_trial[key].get(field) != value for field, value in raw.items()):
            raise ValueError(f"Q5 graded/raw runtime provenance mismatch: {key}")
    control_systems = (
        {Q5_ESCALATE_EVERYTHING_CONTROL, Q5_ALWAYS_HUMAN_REVIEW_CONTROL}
        if protocol.version is Q5ProtocolVersion.v4
        else {Q5_ESCALATE_EVERYTHING_CONTROL}
    )
    expected_controls = {
        (system, case_id, run_index)
        for system in control_systems
        for case_id in raw_manifest["case_ids"]
        for run_index in range(1, int(raw_manifest["k"]) + 1)
    }
    actual_controls: set[tuple[str, str, int]] = set()
    for row in analytic_rows:
        if row.get("system") not in control_systems:
            raise ValueError("Q5 analytic control has an invalid system identity")
        key = (
            str(row.get("system") or ""),
            str(row.get("case_id") or ""),
            int(row.get("run_index") or 0),
        )
        if key in actual_controls:
            raise ValueError(f"duplicate Q5 analytic-control row: {key}")
        actual_controls.add(key)
    if actual_controls != expected_controls:
        raise ValueError("Q5 analytic-control trial-key matrix mismatch")
    if summary.get("run_id") != raw_manifest.get("run_id"):
        raise ValueError("Q5 summary run_id provenance mismatch")
    metric_kwargs = {
        "k": int(raw_manifest["k"]),
        "seed": int(raw_manifest["seed"]),
        "bootstrap_resamples": int(raw_manifest["bootstrap"]["resamples"]),
    }
    if protocol.version is Q5ProtocolVersion.v1:
        recomputed = compute_q5_metrics_v1(
            [*graded_rows, *analytic_rows],
            **metric_kwargs,
        )
        expected_gates = evaluate_q5_gates_v1(summary)
        expected_report = render_q5_report_v1(summary, gates)
    elif protocol.version is Q5ProtocolVersion.v2:
        recomputed = compute_q5_metrics_v2(
            [*graded_rows, *analytic_rows],
            **metric_kwargs,
        )
        expected_gates = evaluate_q5_gates_v2(summary)
        expected_report = render_q5_report_v2(summary, gates)
    elif protocol.version is Q5ProtocolVersion.v3:
        recomputed = compute_q5_metrics_v3(
            [*graded_rows, *analytic_rows],
            **metric_kwargs,
        )
        expected_gates = evaluate_q5_gates_v3(summary)
        expected_report = render_q5_report_v3(summary, gates)
    else:
        recomputed = compute_q5_metrics(
            [*graded_rows, *analytic_rows],
            **metric_kwargs,
        )
        expected_gates = evaluate_q5_gates(summary)
        expected_report = render_q5_report(summary, gates)
    control = recomputed["by_system"].pop(Q5_ESCALATE_EVERYTHING_CONTROL, None)
    if control is None:
        raise ValueError("Q5 graded run is missing escalate-everything analytic control")
    disposition_control = recomputed["by_system"].pop(
        Q5_ALWAYS_HUMAN_REVIEW_CONTROL,
        None,
    )
    if protocol.version is Q5ProtocolVersion.v4 and disposition_control is None:
        raise ValueError("Q5 graded run is missing disposition anti-gaming control")
    fixed_table_control = recomputed.pop("fixed_table_control", None)
    if protocol.version in {Q5ProtocolVersion.v3, Q5ProtocolVersion.v4} and not isinstance(
        fixed_table_control,
        dict,
    ):
        raise ValueError("Q5 graded run is missing fixed-table analytic control")
    for field in (
        "schema_version",
        "metric_type",
        "k",
        "seed",
        "bootstrap_resamples",
        "by_system",
        "comparisons",
    ):
        if summary.get(field) != recomputed.get(field):
            raise ValueError(f"Q5 summary metric provenance mismatch: {field}")
    if (summary.get("analytic_controls") or {}).get(
        Q5_ESCALATE_EVERYTHING_CONTROL
    ) != control:
        raise ValueError("Q5 summary analytic-control provenance mismatch")
    if protocol.version is Q5ProtocolVersion.v4 and (
        summary.get("analytic_controls") or {}
    ).get(Q5_ALWAYS_HUMAN_REVIEW_CONTROL) != disposition_control:
        raise ValueError("Q5 disposition-control provenance mismatch")
    if protocol.version in {Q5ProtocolVersion.v3, Q5ProtocolVersion.v4} and (
        summary.get("analytic_controls") or {}
    ).get("q5_semantic_table_rule_control") != fixed_table_control:
        raise ValueError("Q5 fixed-table control provenance mismatch")
    if gates != expected_gates:
        raise ValueError("Q5 gates are not reproducible from the verified summary")
    if (root / "report.md").read_text(encoding="utf-8") != expected_report:
        raise ValueError("Q5 report is not reproducible from summary and gates")
    role = str(raw_manifest.get("model", {}).get("role") or "")
    identities = raw_manifest.get("model", {}).get("identities") or []
    validated_identities = [_validate_manifest_identity(item) for item in identities]
    provider_model_pairs = sorted(
        {
            f"{identity.provider}::{identity.model_name}"
            for identity in validated_identities
        }
    )
    raw_manifest_hash = q5_sha256_file(root / "manifest.json")
    expected_ledger = [
        {
            "verified": True,
            "run_id": raw_manifest["run_id"],
            "model_role": role,
            "raw_manifest_sha256": raw_manifest_hash,
            "git_commit_sha": raw_manifest["git_commit_sha"],
            "prompt_sha256": raw_manifest["prompt"]["sha256"],
            "gold_sha256": sealed_gold_sha256,
            "model_identity_sha256": sorted(
                identity.identity_sha256 for identity in validated_identities
            ),
            "provider_model_pairs": provider_model_pairs,
        }
    ]
    metadata = summary.get("run_metadata") or {}
    expected_metadata = {
        "mode": raw_manifest["mode"],
        "mock_used": raw_manifest["mock_used"],
        "real_run": raw_manifest["real_run"],
        "dataset_partition": raw_manifest["dataset_partition"],
        "model_role": role,
        "verified_run_ledger": expected_ledger,
    }
    if metadata != expected_metadata:
        raise ValueError("Q5 summary run metadata/ledger provenance mismatch")
    if set(summary.get("by_model_role") or {}) != {role}:
        raise ValueError("Q5 summary model-role provenance mismatch")
    role_payload = summary["by_model_role"][role]
    if role_payload != {
        "by_system": summary["by_system"],
        "comparisons": summary["comparisons"],
    }:
        raise ValueError("Q5 summary role metrics provenance mismatch")
    return Q5VerifiedRunManifest(
        run_dir=root.resolve(),
        run_id=str(raw_manifest["run_id"]),
        model_role=role,
        raw_manifest_sha256=raw_manifest_hash,
        graded_manifest_sha256=q5_sha256_file(root / "graded_manifest.json"),
        summary_sha256=q5_sha256_file(root / "summary.json"),
        gates_sha256=q5_sha256_file(root / "gates.json"),
        gold_sha256=sealed_gold_sha256,
        model_identities=validated_identities,
        provider_model_pairs=provider_model_pairs,
        git_commit_sha=str(raw_manifest["git_commit_sha"]),
        prompt_sha256=str(raw_manifest["prompt"]["sha256"]),
        mode=str(raw_manifest["mode"]),
        mock_used=bool(raw_manifest["mock_used"]),
        real_run=bool(raw_manifest["real_run"]),
        protocol_version=protocol.version.value,
    )


def q5_hash_payload(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def q5_sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def q5_read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Q5 artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def q5_read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Q5 artifact not found: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Q5 JSONL row must be an object: {path}:{line_number}")
        rows.append(value)
    return rows


def _validate_manifest_identity(payload: Any) -> Q5ModelIdentity:
    identity = Q5ModelIdentity.model_validate(payload)
    canonical = identity.model_dump(mode="json", exclude={"identity_sha256"})
    if identity.identity_sha256 != q5_hash_payload(canonical):
        raise ValueError("Q5 model identity provenance hash mismatch")
    return identity


def _validate_real_client_instance(model: OpenAICompatibleLLMClient) -> None:
    state = vars(model)
    if "generate" in state or "provider_metadata" in state:
        raise ValueError("Q5 real client methods cannot be replaced per instance")
    required = ("api_key", "base_url", "model_name", "provider", "purpose")
    if any(not isinstance(state.get(field), str) or not state[field] for field in required):
        raise ValueError("Q5 real client instance is not fully initialized")


def _trial_tuple(row: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(row.get("case_id") or ""),
        str(row.get("system") or ""),
        int(row.get("run_index") or 0),
    )


def _normalized_endpoint_host(value: str | None) -> str:
    return (value or "").strip().lower().rstrip(".")


def _verify_hash_mapping(
    root: Path,
    payload: Any,
    *,
    expected_names: frozenset[str],
) -> None:
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(artifacts, dict):
        raise ValueError("Q5 artifact hash manifest is invalid")
    actual_names = set(artifacts)
    if actual_names != set(expected_names):
        raise ValueError(
            "Q5 artifact hash closure mismatch: "
            f"missing={sorted(set(expected_names) - actual_names)}, "
            f"extra={sorted(actual_names - set(expected_names))}"
        )
    resolved_root = root.resolve()
    for filename, expected in artifacts.items():
        path = (resolved_root / filename).resolve()
        if resolved_root not in path.parents:
            raise ValueError(f"Q5 artifact hash path escapes run directory: {filename}")
        if not path.is_file() or q5_sha256_file(path) != expected:
            raise ValueError(f"Q5 artifact hash mismatch: {filename}")
