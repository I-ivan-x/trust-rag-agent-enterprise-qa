from __future__ import annotations

from types import SimpleNamespace

from scripts import sweep_evidence_gate as sweep


def test_default_sweep_has_five_config_points() -> None:
    points = sweep._parse_sweep_points(sweep.DEFAULT_CONFIG_SPECS)

    assert len(points) == 5
    assert points[0].label == "default"
    assert points[0].config.min_support_count == 1
    assert points[0].config.min_score is None


def test_sweep_writes_summary(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_run_eval(**kwargs):
        calls.append(kwargs)
        label = kwargs["run_id"]
        run_dir = tmp_path / label
        run_dir.mkdir()
        return {
            "run_id": label,
            "run_dir": run_dir.as_posix(),
            "summary_metrics": {
                "final_gated": {
                    "cases": 1,
                    "false_refusal_rate": 0.0,
                    "false_answer_rate": 0.0,
                    "grounded_correctness": 1.0,
                    "refusal_rate": 0.0,
                    "raw_correctness": 1.0,
                    "citation_valid": 1.0,
                }
            },
            "llm_call_count": 1,
            "headline_eligible": False,
            "pilot_eligible": True,
        }

    monkeypatch.setattr(sweep, "run_eval", fake_run_eval)
    args = SimpleNamespace(
        split="external",
        systems="final_gated",
        mock_run=True,
        real_run=False,
        output_root=tmp_path,
        sweep_id="test-sweep",
        limit=1,
        case_id=None,
        max_cases=None,
        sleep_seconds=0.0,
        max_output_tokens=None,
        trust_gate_policy="neighbor_tolerant",
        configs=[
            "default:min_support_count=1,min_score=none",
            "score0:min_support_count=1,min_score=0",
        ],
        write_reports=False,
    )

    summary = sweep.run_sweep(args)

    assert len(calls) == 2
    assert calls[1]["evidence_gate_config"].min_score == 0.0
    assert calls[1]["trust_gate_policy"] == "neighbor_tolerant"
    assert summary["config_count"] == 2
    assert (tmp_path / "sweep_summary.json").exists()
    assert (tmp_path / "sweep_results.jsonl").exists()
