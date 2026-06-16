"""Report rendering."""

from __future__ import annotations

import json

from .models import Evaluation


def render_text(evaluation: Evaluation) -> str:
    lines = [
        f"Scenario: {evaluation.scenario_id}",
        f"Domain: {evaluation.domain}",
        f"Score: {evaluation.score:.2f}",
        f"Decision: {evaluation.decision}",
        f"Critical issues: {len(evaluation.critical_issues)}",
        f"Warnings: {len(evaluation.warnings)}",
        "",
        "Checks:",
    ]
    for check in evaluation.checks:
        icon = "PASS" if check.passed else "FAIL"
        lines.append(f"- {icon} [{check.severity}] {check.check_id}: {check.message}")
    return "\n".join(lines)


def render_markdown(evaluation: Evaluation) -> str:
    lines = [
        f"# Evaluation: {evaluation.scenario_id}",
        "",
        f"- Domain: `{evaluation.domain}`",
        f"- Score: `{evaluation.score:.2f}`",
        f"- Decision: `{evaluation.decision}`",
        f"- Critical issues: `{len(evaluation.critical_issues)}`",
        f"- Warnings: `{len(evaluation.warnings)}`",
        "",
        "| Check | Severity | Result | Message |",
        "| --- | --- | --- | --- |",
    ]
    for check in evaluation.checks:
        result = "PASS" if check.passed else "FAIL"
        lines.append(f"| `{check.check_id}` | {check.severity} | {result} | {check.message} |")
    return "\n".join(lines)


def render_json(evaluation: Evaluation) -> str:
    return json.dumps(evaluation.to_dict(), indent=2)


def render_batch_json(evaluations: list[Evaluation]) -> str:
    return json.dumps([evaluation.to_dict() for evaluation in evaluations], indent=2)
