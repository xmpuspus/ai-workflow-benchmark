"""Build portable summaries from saved run-result files without executing tools."""

from __future__ import annotations

import html
from collections import Counter
from pathlib import Path

from awb.core.results import ResultRecorder

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
    return {
        "status": "evidence_available",
        "run_dir": str(run_dir),
        "counts": counts,
        "tools": dict(sorted(tools.items())),
        "failed_tasks": failed,
        "next_step": "Inspect failed tasks and traces before changing the workflow.",
    }


def render_text(report: dict) -> str:
    """Render the stable report payload for a terminal without Rich markup."""
    counts = report["counts"]
    lines = [
        f"Evidence report: {report['status']}",
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
    status = html.escape(report["status"])
    run_dir = html.escape(report["run_dir"])
    next_step = html.escape(report["next_step"])
    style = (
        "body{font:16px system-ui;max-width:720px;margin:3rem auto;padding:0 1rem;color:#17202a}"
        "table{border-collapse:collapse}th,td{padding:.45rem .8rem;border-bottom:1px solid #d8dee4;"
        "text-align:left}.status{font-weight:700}"
    )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>AWB evidence report</title>"
        f"<style>{style}</style><main><h1>AWB evidence report</h1>"
        f'<p class="status">{status}</p><p>Run directory: <code>{run_dir}</code></p>'
        f"<table>{rows}</table><p>Failed tasks: {html.escape(failed)}</p>"
        f"<p>Next step: {next_step}</p></main></html>"
    )
