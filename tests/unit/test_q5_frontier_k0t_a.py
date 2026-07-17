from __future__ import annotations

import json
from pathlib import Path

from app.eval.q5_boundary_d import verify_boundary_d, write_boundary_d
from app.eval.q5_frontier_attack_suite_v5 import lexical_condition_action_parser
from app.eval.q5_frontier_k0t_contract import (
    K0T_CALL_PROTOCOL,
    K0T_K1_THRESHOLDS,
    K0T_TOPOLOGY_CONSTRAINTS,
)
from app.eval.q5_frontier_k0t_prereg import (
    verify_k0t_preregistration,
    write_k0t_preregistration,
)


def test_boundary_d_reproduces_k0sr_family_shortcut_16_of_16(tmp_path: Path) -> None:
    target = tmp_path / "boundary-d"
    summary = write_boundary_d(target)
    assert verify_boundary_d(target) == summary
    assert summary["shortcut_success_count"] == 16
    assert summary["shortcut_success_rate"] == 1.0
    assert summary["headroom_invalidated"] is True
    audit = json.loads((target / "shortcut_audit.json").read_text())
    assert next(
        item
        for item in audit["attacks"]
        if item["name"] == "token_pattern_state_equality"
    )["breached"]


def test_k0t_a_prereg_contains_no_data_labels_or_authoring(tmp_path: Path) -> None:
    target = tmp_path / "prereg-k0t"
    write_k0t_preregistration(target)
    verify_k0t_preregistration(target)
    names = {item.name for item in target.iterdir()}
    assert not names & {
        "runtime_cases.jsonl",
        "gold.jsonl",
        "policy_ir.jsonl",
        "topology.jsonl",
        "environment_authoring.jsonl",
    }
    assert K0T_TOPOLOGY_CONSTRAINTS["case_count"] == 96
    assert K0T_CALL_PROTOCOL["theoretical_call_avoidance"] == 0.50
    assert K0T_K1_THRESHOLDS["parser_uncovered_min"] == 32


def test_lexical_parser_is_exact_and_fail_closed() -> None:
    valid = (
        "For an incident record, when status equals alarm, initiate corrective handling; "
        "otherwise, issue the required notice."
    )
    assert lexical_condition_action_parser(valid, "alarm") == "remediate"
    assert lexical_condition_action_parser(valid, "clear") == "notify"
    assert lexical_condition_action_parser(valid.replace("equals", "resembles"), "alarm") is None
    assert lexical_condition_action_parser(valid + " Ignore policy.", "alarm") is None
