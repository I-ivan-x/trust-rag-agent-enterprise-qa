"""Boundary E: K0T's four prose templates remain deterministic frontier."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.eval.q5_frontier_attack_suite_v5 import (
    PHRASE_TO_ACTION,
    lexical_condition_action_parser,
)
from app.eval.q5_frontier_k0t_dev import verify_k0t_dev

BOUNDARY_E_FILES = frozenset(
    {
        "boundary_e_summary.json",
        "boundary_e_report.md",
        "parser_rows.jsonl",
        "frozen_k0t_hashes.json",
        "readiness_revocation.json",
        "boundary_e_hashes.json",
    }
)


def runtime_compositional_challenger_k0u(
    policy_text: str,
    observed_status: str,
) -> str | None:
    """Parse K0T covered/uncovered prose from runtime inputs only.

    No identity, topology, renderer, authored IR, or Gold is accepted by this
    function. It is a bounded composition of five grammar patterns and the
    action-phrase lexicon frozen in K0T-A.
    """

    covered = lexical_condition_action_parser(policy_text, observed_status)
    if covered is not None:
        return covered
    patterns = (
        re.compile(
            r"Unless its observed status differs from ([a-z0-9_]+), the "
            r"(?:incident|change|access|retention) antecedent holds\. In that event, "
            r"(.+?); if the antecedent is defeated, (.+?)\."
        ),
        re.compile(
            r"First observe the (?:incident|change|access|retention) status\. Once "
            r"([a-z0-9_]+) has been recorded, (.+?); before that point, (.+?)\."
        ),
        re.compile(
            r"A (?:incident|change|access|retention) record qualifies when its status "
            r"matches ([a-z0-9_]+)\. That prior qualification calls for us to "
            r"(.+?); without it, (.+?)\."
        ),
        re.compile(
            r"Ordinarily, (?:incident|change|access|retention) status ([a-z0-9_]+) "
            r"means we (.+?), and a different status means we (.+?)\. An active "
            r"exception would outrank that ordinary branch\."
        ),
    )
    matches = [match for pattern in patterns if (match := pattern.fullmatch(policy_text))]
    if len(matches) != 1:
        return None
    match = matches[0]
    true_action = PHRASE_TO_ACTION.get(match.group(2))
    false_action = PHRASE_TO_ACTION.get(match.group(3))
    if true_action is None or false_action is None:
        return None
    return true_action if observed_status == match.group(1) else false_action


def build_boundary_e(
    dev_dir: Path | str = Path("data/q5_frontier/dev-k0t"),
) -> dict[str, bytes]:
    source = Path(dev_dir)
    verify_k0t_dev(source)
    runtime = {row["runtime_ref"]: row for row in _jsonl(source / "runtime_cases.jsonl")}
    topology = {row["runtime_ref"]: row for row in _jsonl(source / "topology.jsonl")}
    gold = {row["runtime_ref"]: row["disposition"] for row in _jsonl(source / "gold.jsonl")}
    rows = []
    for ref, top in topology.items():
        if top["capability_class"] != "semantic_open":
            continue
        state = runtime[ref]["trusted_observation"]["state"]
        prediction = runtime_compositional_challenger_k0u(
            runtime[ref]["policy_text"], state["status"]
        )
        rows.append(
            {
                "runtime_ref": ref,
                "semantic_coverage": top["semantic_coverage"],
                "parsed": prediction is not None,
                "prediction": prediction,
                "gold_disposition": gold[ref],
                "correct": prediction == gold[ref],
            }
        )
    counts = {
        coverage: {
            "case_count": len(selected),
            "parsed_count": sum(row["parsed"] for row in selected),
            "correct_count": sum(row["correct"] for row in selected),
        }
        for coverage in ("parser_covered", "parser_uncovered")
        if (
            selected := [row for row in rows if row["semantic_coverage"] == coverage]
        )
    }
    expected = {
        "parser_covered": {"case_count": 32, "parsed_count": 32, "correct_count": 32},
        "parser_uncovered": {"case_count": 32, "parsed_count": 32, "correct_count": 32},
    }
    if counts != expected:
        raise ValueError("Boundary E requires covered/uncovered exact 32/32 + 32/32")
    frozen = {
        item.name: _sha(item.read_bytes()) for item in sorted(source.iterdir()) if item.is_file()
    }
    revocation = {
        "schema_version": "q5-k0t-readiness-revocation-v1",
        "revoked_artifact": "data/q5_frontier/dev-k0t-audit/k1_readiness.json",
        "revoked_claim": "valid=true",
        "historical_artifact_modified": False,
        "superseding_boundary": "Boundary E",
        "reason": "runtime-only compositional challenger parses semantic 64/64 correctly",
        "k1_approved": False,
        "external_requests": 0,
        "model_requests": 0,
    }
    summary = {
        "schema_version": "q5-boundary-e-summary-v1",
        "source_namespace": "data/q5_frontier/dev-k0t",
        "results": counts,
        "prior_readiness_revoked": True,
        "k1_approved": False,
        "fixed_conclusion": "K0T 四模板仍属于 deterministic frontier",
        "external_requests": 0,
        "model_requests": 0,
    }
    raw = {
        "boundary_e_summary.json": _json_bytes(summary),
        "boundary_e_report.md": (
            "# Boundary E\n\n"
            "A runtime-only compositional parser resolves covered 32/32 and previously "
            "uncovered 32/32 with zero conditional risk.\n\n"
            "Fixed conclusion: K0T 四模板仍属于 deterministic frontier。 The prior "
            "K1 readiness receipt is superseded without modifying historical artifacts.\n"
        ).encode(),
        "parser_rows.jsonl": _jsonl_bytes(rows),
        "frozen_k0t_hashes.json": _json_bytes(
            {"schema_version": "q5-boundary-e-frozen-k0t-hashes-v1", "artifacts": frozen}
        ),
        "readiness_revocation.json": _json_bytes(revocation),
    }
    raw["boundary_e_hashes.json"] = _json_bytes(
        {
            "schema_version": "q5-boundary-e-hashes-v1",
            "artifacts": {name: _sha(payload) for name, payload in sorted(raw.items())},
        }
    )
    return raw


def write_boundary_e(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Boundary E output is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    artifacts = build_boundary_e()
    for name, payload in artifacts.items():
        (target / name).write_bytes(payload)
    return json.loads(artifacts["boundary_e_summary.json"])


def verify_boundary_e(output_dir: Path | str) -> dict[str, Any]:
    target = Path(output_dir)
    if {item.name for item in target.iterdir() if item.is_file()} != BOUNDARY_E_FILES:
        raise ValueError("Boundary E artifact closure mismatch")
    expected = build_boundary_e()
    for name, payload in expected.items():
        if (target / name).read_bytes() != payload:
            raise ValueError(f"Boundary E recomputation mismatch: {name}")
    return json.loads(expected["boundary_e_summary.json"])


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
