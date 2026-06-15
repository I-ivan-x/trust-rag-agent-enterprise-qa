from __future__ import annotations

from app.eval.judge.agreement import (
    AuditExample,
    agreement_metrics,
    cohen_kappa_binary,
    probe_floor_metrics,
    select_candidate,
    verdict_row,
)
from app.eval.judge.base import JudgeVerdict


def test_agreement_metrics_binary_exact_and_strata() -> None:
    anchors = [
        AuditExample("a1", "c1", "external", "claim", ["text"], "supported", False),
        AuditExample("a2", "c2", "external", "claim", ["text"], "weak", False),
        AuditExample("a3", "c3", "obfuscated", "claim", ["text"], "supported", False),
    ]
    rows = [
        verdict_row(
            candidate_id="custom",
            example=anchors[0],
            verdict=JudgeVerdict(label="supported"),
        ),
        verdict_row(
            candidate_id="custom",
            example=anchors[1],
            verdict=JudgeVerdict(label="unsupported"),
        ),
        verdict_row(
            candidate_id="custom",
            example=anchors[2],
            verdict=JudgeVerdict(label="weak"),
        ),
    ]

    metrics = agreement_metrics(anchors, rows, bootstrap_samples=10)

    assert metrics["binary_agreement"] == 2 / 3
    assert metrics["exact_agreement"] == 1 / 3
    assert metrics["per_stratum"]["obfuscated"]["binary_agreement"] is None


def test_cohen_kappa_binary_handles_perfect_agreement() -> None:
    assert cohen_kappa_binary(["supported"], ["supported"]) == 1.0


def test_probe_gate_requires_four_of_five_correct() -> None:
    probes = [
        AuditExample(f"p{i}", f"c{i}", "probe", "claim", ["text"], "unsupported", i > 3)
        for i in range(1, 6)
    ]
    rows = []
    for index, probe in enumerate(probes, start=1):
        rows.append(
            verdict_row(
                candidate_id="custom",
                example=probe,
                verdict=JudgeVerdict(
                    label="unsupported" if index <= 4 else "supported",
                    wrong_side=probe.wrong_side_citation if index <= 4 else False,
                ),
            )
        )

    metrics = probe_floor_metrics(probes, rows)

    assert metrics["custom"]["correct"] == 4
    assert metrics["custom"]["passes_probe_gate"] is True


def test_selection_requires_g2_and_probe_gate() -> None:
    selection = select_candidate(
        metrics={
            "ragas": {"binary_agreement": 1.0},
            "custom": {"binary_agreement": 1.0},
        },
        probe_metrics={
            "ragas": {"passes_probe_gate": False},
            "custom": {"passes_probe_gate": True},
        },
    )

    assert selection["deploy_judge"] is True
    assert selection["selected_candidate"] == "custom"
