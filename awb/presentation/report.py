"""Build portable summaries from saved run-result files without executing tools."""

from __future__ import annotations

import html
import shlex
from collections import Counter
from pathlib import Path

from awb.core.results import ResultRecorder
from awb.scoring.cohorts import assess_cohort_coverage

EMPTY_NEXT_STEP = "Run an explicit benchmark, then render this saved evidence with awb report last."


def build_report(run_dir: Path) -> dict:
    """Summarize a saved run directory; never inspect adapters or task sources."""
    results = ResultRecorder(run_dir.parent).load_run(run_dir)
    task_ids = {result.task_id for result in results}
    passed = sum(result.outcome.success for result in results)
    counts = {
        "results": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "tasks": len(task_ids),
    }
    if not results:
        return {
            "status": "no_evidence",
            "run_dir": str(run_dir),
            "counts": counts,
            "next_step": EMPTY_NEXT_STEP,
        }

    tools = Counter(result.tool for result in results)
    failed = sorted({result.task_id for result in results if not result.outcome.success})
    measured = {"measured_clean", "measured_findings"}
    coverage = {}
    for name, field in (
        ("security", "security_status"),
        ("regression", "test_regressions_status"),
        ("lint", "lint_status"),
    ):
        statuses = Counter(getattr(r.quality, field, "missing") for r in results)
        coverage[name] = {
            "measured": sum(statuses[s] for s in measured),
            "total": len(results),
            "statuses": dict(statuses),
        }
    cohort = assess_cohort_coverage(results)
    attempts = []
    for r in results:
        error = r.outcome.error
        attempts.append(
            {
                "task_id": r.task_id,
                "tool": r.tool,
                "correctness": "passed" if r.outcome.success else "failed",
                "execution_status": getattr(r, "execution_status", "unknown"),
                "stage": getattr(r, "execution_stage", "unknown"),
                "termination_reason": getattr(r, "termination_reason", ""),
                "error": str(error) if error else None,
                "partial_credit": r.outcome.partial_credit_score,
                "partial_credit_max": r.outcome.partial_credit_max,
                "elapsed_seconds": r.metrics.wall_clock_seconds,
                "loaded_instruction_files": getattr(r, "loaded_instruction_files", []),
                "allowed_edit_paths": getattr(r, "allowed_edit_paths", []),
                "trace_path": r.trace_path or None,
                "recovery_command": shlex.join(
                    ["awb", "run", r.tool, "--task", r.task_id, "--runs", "1", "--dry-run"]
                ),
                "recovery_note": (
                    "Preview a new attempt. It does not resume the original experiment."
                ),
            }
        )
    cost_complete = all(getattr(r, "usage_status", "unknown") == "complete" for r in results)
    return {
        "status": "evidence_available",
        "run_dir": str(run_dir),
        "counts": counts,
        "tools": dict(sorted(tools.items())),
        "failed_tasks": failed,
        "coverage": coverage,
        "comparison": {
            "eligible": cohort.eligible,
            "reasons": cohort.reasons,
            "selected_task_ids": cohort.selected_task_ids,
            "requested_repeats": cohort.requested_repeats,
            "reason": (
                "One complete recorded cohort. Check measurement coverage before comparing scores."
                if cohort.eligible
                else "Comparison unavailable. This run lacks complete identity or repeat coverage."
            ),
        },
        "cost": {
            "recorded_usd": sum(r.cost.estimated_cost_usd for r in results),
            "complete": cost_complete,
            "interpretation": "Recorded estimate"
            if cost_complete
            else "Unknown total; recorded usage may be incomplete",
        },
        "attempts": attempts,
        "next_step": "Inspect failed tasks and traces before changing the workflow.",
    }


def render_text(report: dict) -> str:
    """Render the stable report payload for a terminal without Rich markup."""
    counts = report["counts"]
    lines = [
        f"Evidence report: {report['status'].replace('_', ' ')}",
        f"Run directory: {report['run_dir']}",
    ]
    lines.append(
        "Results: {results} | Passed: {passed} | Failed: {failed} | Tasks: {tasks}".format(**counts)
    )
    if report.get("tools"):
        tools = ", ".join(f"{name} ({n})" for name, n in report["tools"].items())
        lines.append("Tools: " + tools)
    if report.get("failed_tasks"):
        lines.append("Failed tasks: " + ", ".join(report["failed_tasks"]))
    if report.get("coverage"):
        for name, coverage in report["coverage"].items():
            lines.append(
                f"{name.title()} measured: {coverage['measured']}/{coverage['total']}; "
                "remaining evidence is unknown or failed"
            )
        lines.append("Comparison: " + report["comparison"]["reason"])
        lines.append("Cost: " + report["cost"]["interpretation"])
        for attempt in report["attempts"]:
            lines.append(
                f"{attempt['task_id']}: {attempt['correctness']}; "
                f"execution {attempt['execution_status']}; stage {attempt['stage']}"
            )
            if attempt["correctness"] != "passed":
                lines.append("Preview recovery: " + attempt["recovery_command"])
    lines.append("Next step: " + report["next_step"])
    return "\n".join(lines)


def render_html(report: dict) -> str:
    """Render a standalone, escaped local HTML summary."""
    counts = report["counts"]
    rows = "".join(
        f"<tr><th>{html.escape(key.title())}</th><td>{value}</td></tr>"
        for key, value in counts.items()
    )
    failed = ", ".join(report.get("failed_tasks", [])) or "None"
    status = html.escape(report["status"].replace("_", " ").title())
    run_dir = html.escape(report["run_dir"])
    next_step = html.escape(report["next_step"])
    evidence = ""
    if report.get("coverage"):
        evidence = (
            "<h2>Evidence coverage</h2><ul>"
            + "".join(
                f"<li>{html.escape(name.title())}: "
                f"{values['measured']}/{values['total']} measured. "
                "Remaining evidence is unknown or failed.</li>"
                for name, values in report["coverage"].items()
            )
            + "</ul>"
        )
        evidence += f"<p>{html.escape(report['comparison']['reason'])}</p>"
        reasons = report["comparison"].get("reasons", [])
        if reasons:
            evidence += (
                "<details><summary>Why this run cannot be compared</summary><ul class='reasons'>"
                + "".join(f"<li>{html.escape(reason.replace('_', ' '))}</li>" for reason in reasons)
                + "</ul></details>"
            )
        evidence += f"<p>Cost: {html.escape(report['cost']['interpretation'])}</p>"
        for attempt in report["attempts"]:
            fields = (
                ("Tool", attempt["tool"]),
                ("Execution", attempt["execution_status"].replace("_", " ")),
                ("Last stage", attempt["stage"]),
                ("Partial credit", f"{attempt['partial_credit']}/{attempt['partial_credit_max']}"),
                ("Elapsed time", f"{attempt['elapsed_seconds']:.1f} seconds"),
                ("Termination", attempt["termination_reason"] or "Not recorded"),
                ("Error", attempt["error"] or "None recorded"),
                ("Trace", attempt["trace_path"] or "Not recorded"),
            )
            evidence += (
                f"<details><summary>{html.escape(attempt['task_id'])}: "
                f"{html.escape(attempt['correctness'])}</summary><div class='attempt'><dl>"
                + "".join(
                    f"<dt>{label}</dt><dd>{html.escape(str(value))}</dd>" for label, value in fields
                )
                + "</dl><p>Preview a new attempt:</p><pre>"
                + html.escape(attempt["recovery_command"])
                + "</pre><p>"
                + html.escape(attempt["recovery_note"])
                + "</p></div></details>"
            )
    style = (
        "body{font:16px system-ui;max-width:720px;margin:3rem auto;padding:0 1rem;color:#17202a}"
        "table{border-collapse:collapse}th,td{padding:.45rem .8rem;border-bottom:1px solid #d8dee4;"
        "text-align:left}.status{font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        "details{margin:1rem 0;border:1px solid #d8dee4}"
        "summary{min-height:44px;box-sizing:border-box;padding:.75rem;cursor:pointer}"
        "details pre{padding:0 .75rem}code{overflow-wrap:anywhere}"
        ".attempt{padding:0 .75rem}dt{font-weight:600;margin-top:.6rem}"
        "dd{margin:0;overflow-wrap:anywhere}"
        ".reasons{padding:0 2rem 1rem}"
    )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>AWB evidence report</title>"
        f"<style>{style}</style><main><h1>AWB evidence report</h1>"
        f'<p class="status">{status}</p><p>Run directory: <code>{run_dir}</code></p>'
        f"<table>{rows}</table><p>Failed tasks: {html.escape(failed)}</p>"
        f"{evidence}<p>Next step: {next_step}</p></main></html>"
    )
