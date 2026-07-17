from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.eval.q5_frontier_k0u_audit import (
    K0U_AUDIT_FILES,
    posthoc_complexity_attestation,
    verify_k0u_audit,
    write_k0u_audit,
)
from app.eval.q5_frontier_k0u_posthoc import independent_runtime_challenger
from app.schemas.q5_frontier import FrontierDisposition
from app.schemas.q5_frontier_v6 import PracticalObservationInput, PracticalRuntimeInput


@pytest.fixture()
def audit_dir(tmp_path: Path) -> Path:
    target = tmp_path / "audit"
    write_k0u_audit(target)
    return target


def test_dual_attack_scores_uncovered_separately_and_forms_boundary(audit_dir: Path) -> None:
    readiness = verify_k0u_audit(audit_dir)
    assert {item.name for item in audit_dir.iterdir()} == K0U_AUDIT_FILES
    metrics = _json(audit_dir / "attack_metrics.json")["parsers"]
    prereg = metrics["preregistered_practical_parser"]
    assert prereg["parser_covered"] == {
        "case_count": 32,
        "parsed_count": 32,
        "correct_count": 32,
        "coverage": 1.0,
        "conditional_accuracy": 1.0,
        "conditional_risk": 0.0,
        "overall_accuracy": 1.0,
        "abstention_count": 0,
    }
    assert prereg["parser_uncovered"]["parsed_count"] == 0
    posthoc = metrics["independent_runtime_challenger"]["parser_uncovered"]
    assert posthoc["case_count"] == 32
    assert posthoc["parsed_count"] == 30
    assert posthoc["coverage"] == 0.9375
    assert posthoc["conditional_accuracy"] == 1.0
    assert posthoc["conditional_risk"] == 0.0
    assert posthoc["abstention_count"] == 2
    boundary = _json(audit_dir / "boundary_f_summary.json")
    assert boundary["formed"] is True
    assert readiness["valid"] is False
    assert readiness["k1_approved"] is False
    assert readiness["oracle_resolvable_abstentions"] == 2
    assert readiness["hybrid_theoretical_call_avoidance"] == 0.5
    assert readiness["blockers"] == [
        "posthoc_practical_frontier_breached",
        "oracle_resolvable_abstentions_below_minimum",
    ]


def test_posthoc_parser_is_runtime_only_bounded_and_generalizes() -> None:
    attestation = posthoc_complexity_attestation()
    assert attestation["valid"] is True
    assert all(attestation["checks"].values())
    matching = _runtime(
        "A current record on signal_901 sends the required notice; "
        "otherwise leave governance unchanged.",
        "signal_901",
    )
    renamed = _runtime(
        "An irrelevant audit sentence has no force. A current record on signal_777 "
        "sends the required notice; otherwise leave governance unchanged.",
        "other_777",
    )
    reversed_order = _runtime(
        "Corrective handling is the fallback; signal_808 instead makes the record stale.",
        "signal_808",
    )
    assert independent_runtime_challenger(matching).disposition == FrontierDisposition.notify
    assert independent_runtime_challenger(renamed).disposition == FrontierDisposition.no_action
    assert (
        independent_runtime_challenger(reversed_order).disposition == FrontierDisposition.mark_stale
    )
    assert (
        independent_runtime_challenger(
            _runtime("An unrecognized policy dialect.", "signal_001")
        ).status
        == "abstain"
    )


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "rows", "metrics", "complexity", "lineage", "boundary", "readiness"],
)
def test_k0u_audit_rehashed_mutations_fail_closed(
    audit_dir: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    target = tmp_path / mutation
    shutil.copytree(audit_dir, target)
    if mutation == "missing":
        (target / "audit_report.md").unlink()
    elif mutation == "extra":
        (target / "extra.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "rows":
        rows = _jsonl(target / "audit_rows.jsonl")
        rows[-1]["correct"] = not rows[-1]["correct"]
        _write_jsonl(target / "audit_rows.jsonl", rows)
        _rehash(target)
    else:
        names = {
            "metrics": "attack_metrics.json",
            "complexity": "posthoc_complexity.json",
            "lineage": "lineage_receipt.json",
            "boundary": "boundary_f_summary.json",
            "readiness": "k1_readiness.json",
        }
        name = names[mutation]
        payload = _json(target / name)
        if mutation == "metrics":
            payload["parsers"]["independent_runtime_challenger"]["parser_uncovered"]["coverage"] = (
                0.0
            )
        elif mutation == "complexity":
            payload["valid"] = False
        elif mutation == "lineage":
            payload["posthoc_absent_at_data_commit"] = False
        elif mutation == "boundary":
            payload["formed"] = False
        else:
            payload["valid"] = True
            payload["blockers"] = []
        _write_json(target / name, payload)
        _rehash(target)
    with pytest.raises(ValueError):
        verify_k0u_audit(target)


def _runtime(policy_text: str, status: str) -> PracticalRuntimeInput:
    return PracticalRuntimeInput(
        policy_text=policy_text,
        observation=PracticalObservationInput(
            status=status,
            scope="production",
            temporal_state="current",
            exception_active=False,
            authorized=True,
            successful=True,
        ),
        legal_dispositions=list(FrontierDisposition),
    )


def _rehash(target: Path) -> None:
    artifacts = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(target.iterdir())
        if item.is_file() and item.name != "audit_hashes.json"
    }
    _write_json(
        target / "audit_hashes.json",
        {"schema_version": "q5-k0u-audit-hashes-v1", "artifacts": artifacts},
    )


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
