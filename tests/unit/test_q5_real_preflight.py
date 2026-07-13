from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.llm.llm_client import DeepSeekLLMClient, get_llm_client
from scripts import preflight_q5_real as preflight
from scripts.preflight_q5_real import (
    Q5_REAL_CASE_COUNT,
    Q5_REAL_K,
    Q5_REAL_PREFLIGHT_SCHEMA,
    Q5_REAL_SYSTEMS,
    Q5_V3_AUTHORING_SHA256,
    _budget,
    _real_command,
    _validate_mock_topology,
    _validate_v3_mock_metrics,
    build_parser,
)


def _topology_fixture() -> tuple[list[str], list[dict], dict]:
    case_ids = [f"q5-dev-case-{index:02d}" for index in range(Q5_REAL_CASE_COUNT)]
    rows = [
        {
            "case_id": case_id,
            "system": system,
            "run_index": run_index,
            "llm_calls": 0 if system == "q5_rule_agent" else 1,
        }
        for case_id in case_ids
        for system in Q5_REAL_SYSTEMS
        for run_index in range(1, Q5_REAL_K + 1)
    ]
    manifest = {
        "systems": list(Q5_REAL_SYSTEMS),
        "case_ids": sorted(case_ids),
        "k": Q5_REAL_K,
        "trial_count": len(rows),
        "expected_trial_count": len(rows),
        "artifact_row_counts": {"results.jsonl": len(rows)},
    }
    return case_ids, rows, manifest


def test_q5_real_preflight_budget_is_observability_only() -> None:
    expected = _budget(210, 512)
    hard = _budget(396, 512)

    assert expected["call_count"] == 210
    assert expected["total_token_upper"] == 1_827_840
    assert expected["cache_miss_cost_upper_usd"] > 0.20
    assert hard["call_count"] == 396
    assert hard["cache_miss_cost_upper_usd"] > expected[
        "cache_miss_cost_upper_usd"
    ]


def test_q5_real_preflight_k3_parser_and_command_are_explicit_and_gold_free() -> None:
    args = build_parser().parse_args(
        [
            "--mock-run",
            "mock-run",
            "--output",
            "preflight.json",
            "--real-run-id",
            "q5-real-dev-primary-k3",
        ]
    )

    command = _real_command(args)

    assert args.k == 3
    assert args.seed == 20260712
    assert "py -m uv run --frozen python" in command
    assert "--mode real" in command
    assert "--model-role primary" in command
    assert "--provider deepseek" in command
    assert "--model deepseek-v4-flash" in command
    assert "--temperature 0" in command
    assert "--max-output-tokens 512" in command
    assert "--timeout-seconds 30" in command
    assert "--thinking-mode disabled" in command
    assert "--k 3" in command
    assert "--seed 20260712" in command
    assert "--gold" not in command
    assert "q5/test" not in command


def test_q5_real_preflight_accepts_complete_324_trial_topology() -> None:
    case_ids, rows, manifest = _topology_fixture()

    topology = _validate_mock_topology(
        rows,
        manifest,
        case_ids=case_ids,
        systems=Q5_REAL_SYSTEMS,
        k=Q5_REAL_K,
    )

    assert topology["trial_count"] == 324
    assert topology["unique_trial_key_count"] == 324
    assert topology["run_indexes"] == [1, 2, 3]
    assert topology["rows_per_run_index"] == {"1": 108, "2": 108, "3": 108}
    assert topology["expected_total_calls"] == 216


def test_q5_real_preflight_v3_metrics_fail_closed_on_tamper() -> None:
    summary, gates = _metric_anchor_fixture()
    _validate_v3_mock_metrics(summary, gates)

    summary["by_system"]["q5_rule_agent"][
        "trajectory_qualified_success_by_stratum"
    ]["semantic"] = 0.75
    with pytest.raises(ValueError, match="0.50"):
        _validate_v3_mock_metrics(summary, gates)


def test_q5_real_preflight_rejects_missing_run_index() -> None:
    case_ids, rows, manifest = _topology_fixture()
    rows = [row for row in rows if row["run_index"] != 3]

    with pytest.raises(ValueError, match="run indexes"):
        _validate_mock_topology(
            rows,
            manifest,
            case_ids=case_ids,
            systems=Q5_REAL_SYSTEMS,
            k=Q5_REAL_K,
        )


def test_q5_real_preflight_rejects_duplicate_trial_key() -> None:
    case_ids, rows, manifest = _topology_fixture()
    rows.append(deepcopy(rows[0]))

    with pytest.raises(ValueError, match="duplicate trial keys"):
        _validate_mock_topology(
            rows,
            manifest,
            case_ids=case_ids,
            systems=Q5_REAL_SYSTEMS,
            k=Q5_REAL_K,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("system", "q5_injected_agent", "unexpected trial keys"),
        ("case_id", "q5-dev-injected", "unexpected trial keys"),
    ],
)
def test_q5_real_preflight_rejects_wrong_system_or_case(
    field: str,
    value: str,
    message: str,
) -> None:
    case_ids, rows, manifest = _topology_fixture()
    rows[0][field] = value

    with pytest.raises(ValueError, match=message):
        _validate_mock_topology(
            rows,
            manifest,
            case_ids=case_ids,
            systems=Q5_REAL_SYSTEMS,
            k=Q5_REAL_K,
        )


def test_q5_real_preflight_rejects_manifest_k_mismatch() -> None:
    case_ids, rows, manifest = _topology_fixture()
    manifest["k"] = 1

    with pytest.raises(ValueError, match="manifest k"):
        _validate_mock_topology(
            rows,
            manifest,
            case_ids=case_ids,
            systems=Q5_REAL_SYSTEMS,
            k=Q5_REAL_K,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("systems", ["q5_rule_agent"], "manifest systems"),
        ("case_ids", ["q5-dev-injected"], "manifest case IDs"),
    ],
)
def test_q5_real_preflight_rejects_manifest_system_or_case_mismatch(
    field: str,
    value: list[str],
    message: str,
) -> None:
    case_ids, rows, manifest = _topology_fixture()
    manifest[field] = value

    with pytest.raises(ValueError, match=message):
        _validate_mock_topology(
            rows,
            manifest,
            case_ids=case_ids,
            systems=Q5_REAL_SYSTEMS,
            k=Q5_REAL_K,
        )


def test_q5_real_preflight_rejects_mock_execution_commit_mismatch(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _stub_preflight_dependencies(tmp_path, monkeypatch)
    state.verified.git_commit_sha = "b" * 40

    with pytest.raises(SystemExit):
        preflight.main(state.argv)

    receipt = preflight.q5_read_json(state.output)
    assert receipt["valid"] is False
    assert any("execution commit" in error for error in receipt["errors"])


def test_q5_real_preflight_rejects_existing_real_run_directory(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _stub_preflight_dependencies(tmp_path, monkeypatch)
    (tmp_path / "real-runs" / "q5-real-primary-k3").mkdir(parents=True)

    with pytest.raises(SystemExit):
        preflight.main(state.argv)

    receipt = preflight.q5_read_json(state.output)
    assert receipt["valid"] is False
    assert receipt["freeze"]["real_run_directory_absent"] is False
    assert any("already exists" in error for error in receipt["errors"])


def test_q5_real_preflight_large_cost_never_blocks_and_sends_zero_model_requests(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _stub_preflight_dependencies(tmp_path, monkeypatch)
    monkeypatch.setattr(
        preflight,
        "_budget",
        lambda call_count, max_output_tokens: {
            "call_count": call_count,
            "input_token_upper": 10**15,
            "output_token_upper": 10**15,
            "total_token_upper": 2 * 10**15,
            "cache_miss_cost_upper_usd": 10**9,
        },
    )
    monkeypatch.setattr(
        "app.llm.llm_client.httpx.post",
        lambda *args, **kwargs: pytest.fail("preflight sent an HTTP model request"),
    )

    receipt = preflight.main(state.argv)

    assert receipt["schema_version"] == Q5_REAL_PREFLIGHT_SCHEMA
    assert receipt["valid"] is True
    assert receipt["forecast"]["cost_and_token_observability_only"] is True
    assert receipt["forecast"]["validity_blocking_cost_cap_usd"] is None
    assert receipt["forecast"]["hard_budget"]["cache_miss_cost_upper_usd"] == (
        10**9
    )
    assert receipt["request_policy"] == {
        "completion_requests_sent_during_preflight": 0,
        "http_model_requests_sent_during_preflight": 0,
        "provider_model_calls_during_preflight": 0,
        "tls_handshake_only": True,
    }
    assert state.client.call_count == 0


def test_q5_non_deepseek_client_rejects_thinking_mode_before_construction() -> None:
    with pytest.raises(ValueError, match="only by the explicit DeepSeek client"):
        get_llm_client("xiaomi", thinking_mode="disabled")


def _stub_preflight_dependencies(tmp_path, monkeypatch: pytest.MonkeyPatch):
    execution_commit = "a" * 40
    case_ids, rows, manifest = _topology_fixture()
    tasks = [SimpleNamespace(case_id=case_id) for case_id in case_ids]
    verified = SimpleNamespace(
        git_commit_sha=execution_commit,
        protocol_version="v3",
        mode="mock",
        mock_used=True,
        real_run=False,
        run_id="q5-mock-anchor-k3",
        raw_manifest_sha256="c" * 64,
    )
    client = DeepSeekLLMClient(
        api_key="unit-test-key",
        base_url="https://api.deepseek.com",
        model_name="deepseek-v4-flash",
        temperature=0.0,
        max_output_tokens=512,
        timeout=30.0,
        thinking_mode="disabled",
        purpose="q5_policy",
    )
    output = tmp_path / "preflight-v3.json"
    argv = [
        "--dataset-root",
        str(tmp_path / "dataset"),
        "--mock-run",
        str(tmp_path / "mock-run"),
        "--output",
        str(output),
        "--real-output-root",
        str(tmp_path / "real-runs"),
        "--real-run-id",
        "q5-real-primary-k3",
    ]
    monkeypatch.setattr(preflight, "git_commit_sha", lambda: execution_commit)
    monkeypatch.setattr(preflight, "_worktree_clean", lambda: True)
    monkeypatch.setattr(
        preflight,
        "check_q5_pre_run",
        lambda *args, **kwargs: SimpleNamespace(
            valid=True,
            errors=[],
            sha256=dict(Q5_V3_AUTHORING_SHA256),
        ),
    )
    monkeypatch.setattr(preflight, "load_q5_tasks", lambda path: tasks)
    historical = {
        "v1": SimpleNamespace(
            protocol_version="v1",
            run_id="historical-v1",
            raw_manifest_sha256="1" * 64,
        ),
        "v2": SimpleNamespace(
            protocol_version="v2",
            run_id="historical-v2",
            raw_manifest_sha256="2" * 64,
        ),
    }

    def verify_stub(run_dir, gold_path):
        path = str(run_dir)
        if "q5-dev-real-deepseek" in path and "v2-real" not in path:
            return historical["v1"]
        if "q5-dev-v2-real" in path:
            return historical["v2"]
        return verified

    monkeypatch.setattr(preflight, "verify_q5_graded_run", verify_stub)
    monkeypatch.setattr(preflight, "q5_read_jsonl", lambda path: deepcopy(rows))
    real_q5_read_json = preflight.q5_read_json
    summary, gates = _metric_anchor_fixture()
    monkeypatch.setattr(
        preflight,
        "q5_read_json",
        lambda path: (
            deepcopy(manifest)
            if str(path).endswith("manifest.json")
            else (
                deepcopy(summary)
                if str(path).endswith("summary.json")
                else (
                    deepcopy(gates)
                    if str(path).endswith("gates.json")
                    else real_q5_read_json(path)
                )
            )
        ),
    )
    monkeypatch.setattr(preflight, "get_llm_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(
        preflight,
        "_tls_readiness",
        lambda host, timeout: {
            "ready": True,
            "host": host,
            "port": 443,
            "tls_protocol": "TLSv1.3",
            "cipher": "unit-test",
            "error": None,
        },
    )
    return SimpleNamespace(
        argv=argv,
        output=output,
        verified=verified,
        client=client,
    )


def _metric_anchor_fixture() -> tuple[dict, dict]:
    pair_metrics = {
        "within_policy_paired_count": 18,
        "within_policy_pair_success": 0.5,
        "cross_policy_paired_count": 18,
        "cross_policy_pair_success": 0.5,
        "duplicate_successful_observation_count": 0,
        "post_observation_terminal_rate": 1.0,
    }
    by_system = {
        system: {
            **deepcopy(pair_metrics),
            "trajectory_qualified_success_by_stratum": {"semantic": 0.5},
        }
        for system in Q5_REAL_SYSTEMS
    }
    return (
        {
            "schema_version": "q5-metrics-v3",
            "by_system": by_system,
            "analytic_controls": {
                "q5_semantic_table_rule_control": {
                    "fixed_table_solvability": 0.5
                }
            },
        },
        {
            "schema_version": "q5-gates-v3",
            "gates": {
                gate: {"passed": True}
                for gate in (
                    "G0_safety_floor",
                    "G2_hybrid_noninferiority",
                    "G3_efficiency",
                    "G5_anti_gaming",
                )
            },
        },
    )
