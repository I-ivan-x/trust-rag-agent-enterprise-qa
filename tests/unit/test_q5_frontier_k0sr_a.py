from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.eval.q5_boundary_c import verify_boundary_c, write_boundary_c
from app.eval.q5_frontier_compiler_v4 import compile_policy_ir_v4
from app.eval.q5_frontier_prereg_v4 import (
    FROZEN_SOURCE_PATHS,
    verify_preregistration_v4,
    write_preregistration_v4,
)
from app.schemas.q5_frontier import CanonicalPolicyIR
from app.schemas.q5_frontier_v4 import FrontierRuntimePayloadV4, validate_v4_policy_ir


def _v3_rows(name: str):
    path = Path("data/q5_frontier/dev-v3") / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _fixture():
    runtime = _v3_rows("runtime_cases.jsonl")[0]
    runtime["runtime_ref"] = "parser-uncovered-dev-resource:r001"
    policy_ir = CanonicalPolicyIR.model_validate(_v3_rows("policy_ir.jsonl")[0]["policy_ir"])
    return FrontierRuntimePayloadV4.model_validate(runtime), policy_ir


def test_boundary_c_post_hoc_challenger_is_exact_16_of_16(tmp_path: Path) -> None:
    target = tmp_path / "boundary-c"
    summary = write_boundary_c(target)
    assert verify_boundary_c(target) == summary
    assert summary["post_hoc_compositional_success_count"] == 16
    assert summary["fixed_conclusion"] == "当前四类模板仍在 deterministic frontier"
    assert summary["model_requests"] == 0


def test_prereg_package_contains_only_frozen_contracts(tmp_path: Path) -> None:
    target = tmp_path / "prereg-v4"
    write_preregistration_v4(target)
    verify_preregistration_v4(target)
    names = {item.name for item in target.iterdir()}
    assert not names & {"gold.jsonl", "topology.jsonl", "renderer_manifest.json"}
    metrics = json.loads((target / "metrics_contract.json").read_text())
    assert metrics["token_avoidance"] == "not_evaluated"
    assert "beneficial_evidence" not in metrics["allowed_report_fields"]


@pytest.mark.parametrize(
    "path",
    [
        ("evidence_requirements", "authorized_chunk_required"),
        ("evidence_requirements", "successful_observation_required"),
        ("terminal_safety", "require_authorized_evidence"),
        ("terminal_safety", "require_successful_observation"),
    ],
)
def test_four_requirement_flags_are_const_true(path: tuple[str, str]) -> None:
    _, policy_ir = _fixture()
    payload = policy_ir.model_dump(mode="json")
    payload[path[0]][path[1]] = False
    with pytest.raises(ValueError, match="four v4"):
        validate_v4_policy_ir(CanonicalPolicyIR.model_validate(payload))


def test_resource_observation_family_mismatch_fails_safe() -> None:
    runtime, policy_ir = _fixture()
    payload = policy_ir.model_dump(mode="json")
    payload["evidence_requirements"]["observation_type"] = "inspect_change_state"
    result = compile_policy_ir_v4(CanonicalPolicyIR.model_validate(payload), runtime)
    assert result.disposition == "human_review"
    assert result.resource_observation_family_matches is False


def test_compiler_positive_and_metamorphic_state_change() -> None:
    runtime, policy_ir = _fixture()
    first = compile_policy_ir_v4(policy_ir, runtime)
    mutated = copy.deepcopy(runtime.model_dump(mode="json"))
    mutated["trusted_observation"]["state"]["status"] = "metamorphic_other"
    second = compile_policy_ir_v4(policy_ir, FrontierRuntimePayloadV4.model_validate(mutated))
    assert first.requirement_flags_enforced is True
    assert second.requirement_flags_enforced is True
    assert first.disposition != second.disposition


def test_frozen_source_inventory_is_complete() -> None:
    assert "app/eval/q5_frontier_parser_suite_v4.py" in FROZEN_SOURCE_PATHS
    assert "app/eval/q5_frontier_compiler_v4.py" in FROZEN_SOURCE_PATHS
