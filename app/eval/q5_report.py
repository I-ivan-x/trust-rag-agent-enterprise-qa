"""Compact machine-derived report rendering for Q5 graded artifacts."""

from __future__ import annotations

from typing import Any


def render_q5_report(summary: dict[str, Any], gates: dict[str, Any]) -> str:
    lines = [
        "# Q5 Outcome Evaluation",
        "",
        f"- Run: `{summary.get('run_id', 'unknown')}`",
        f"- Headline eligible: `{gates.get('q5_headline_eligible', False)}`",
        f"- Claim scope: `{gates.get('claim_scope', 'unknown')}`",
        f"- Run valid: `{gates.get('run_valid', False)}`",
        "",
        "## Systems",
        "",
        "| system | task success | trajectory-qualified | terminal correct | "
        "required obs recall | LLM calls | tokens |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for system, metrics in sorted((summary.get("by_system") or {}).items()):
        lines.append(
            "| {system} | {task:.4f} | {qualified:.4f} | {terminal:.4f} | {recall:.4f} | "
            "{calls} | {tokens} |".format(
                system=system,
                task=float(metrics.get("task_success") or 0.0),
                qualified=float(
                    metrics.get("trajectory_qualified_success") or 0.0
                ),
                terminal=float(metrics.get("terminal_action_correct") or 0.0),
                recall=float(metrics.get("required_observation_recall") or 0.0),
                calls=int(metrics.get("llm_calls") or 0),
                tokens=int(metrics.get("total_tokens") or 0),
            )
        )
    control = (summary.get("analytic_controls") or {}).get(
        "q5_escalate_everything_control"
    )
    lines.extend(["", "## Analytic control", ""])
    if isinstance(control, dict):
        lines.extend(
            [
                "- Control: `q5_escalate_everything_control`",
                f"- Task success: `{float(control.get('task_success') or 0.0):.4f}`",
                f"- Escalation rate: `{float(control.get('escalation_rate') or 0.0):.4f}`",
                "- Over-escalation rate: "
                f"`{float(control.get('over_escalation_rate') or 0.0):.4f}`",
                f"- Anti-gaming failure detected: `{control.get('anti_gaming_failure') is True}`",
            ]
        )
    else:
        lines.append("- Missing control: anti-gaming failure; G5 must fail.")
    lines.extend(["", "## Gates", ""])
    for name, gate in (gates.get("gates") or {}).items():
        status = "PASS" if gate.get("passed") else "FAIL"
        lines.append(f"- **{name}**: {status} — {gate.get('description', '')}")
    lines.extend(["", "This report is derived from final-state assertions, not agent prose."])
    return "\n".join(lines) + "\n"
