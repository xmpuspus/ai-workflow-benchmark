"""submit commands — export, submit, compare-submissions."""

from __future__ import annotations

import sys
from datetime import UTC
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import console
from awb.trace.grader import RUBRIC_NAMES


def _mean_trace_summary(trace_grades: list) -> dict | None:
    """Mean of each rubric across runs that produced a gradeable trace.

    Derives the key set from what's actually present rather than a hardcoded
    tuple, so a future rubric addition doesn't silently drop out of the
    submission-level summary again. context_discipline/tool_call_efficiency
    aren't present on every graded run (see grade_trace's docstring), so each
    rubric's mean is taken over the runs that reported it, not zero-filled.
    Known rubrics sort first in their canonical order; anything unrecognized
    sorts after, alphabetically, so output stays deterministic.
    """
    graded = [g for g in trace_grades if g is not None]
    if not graded:
        return None
    present = {k for g in graded for k in g}
    ordered = [k for k in RUBRIC_NAMES if k in present]
    ordered.extend(sorted(k for k in present if k not in RUBRIC_NAMES))
    summary = {}
    for k in ordered:
        values = [g[k] for g in graded if k in g]
        summary[k] = round(sum(values) / len(values), 1)
    return summary


def _load_task_defs() -> dict:
    """Map task_id -> TaskDefinition for files_to_examine lookups. Best-effort."""
    try:
        from awb.core.task_loader import load_all_tasks

        return {t.id: t for t in load_all_tasks()}
    except Exception:
        return {}


def build_submission(results: list, run_dir: Path, task_defs: dict, submitter: str) -> dict:
    """Assemble the shareable submission dict from a run's results.

    Embeds per-run trace grades (null when the trace has no gradeable spans, so
    a non-streaming tool doesn't get a fake 100) and a submission-level
    Production Readiness block, so a regenerated baseline showcases both
    flagship trust features.
    """
    from datetime import datetime

    from awb import __version__
    from awb.scoring.readiness import readiness_from_results
    from awb.trace.grader import grade_trace_or_none

    by_task: dict = {}
    for r in results:
        by_task.setdefault(r.task_id, []).append(r)

    all_trace_grades: list = []
    submission = {
        "spec_version": "awb/v2",
        "submission": {
            "submitter": submitter,
            "submitted_at": datetime.now(UTC).isoformat(),
            "tool": {"name": results[0].tool, "version": results[0].tool_version},
            "model": {"name": results[0].model or "unknown"},
            "environment": {
                "os": results[0].environment.os,
                "hardware_class": "other",
                "hardware_detail": results[0].environment.hardware,
            },
            "awb_version": __version__,
            "readiness": readiness_from_results(results),
        },
        "results": [],
    }

    for task_id, task_results in sorted(by_task.items()):
        files_to_examine = getattr(task_defs.get(task_id), "files_to_examine", []) or []
        runs = []
        for i, r in enumerate(task_results, 1):
            trace_grade = None
            if r.trace_path:
                trace_grade = grade_trace_or_none(
                    run_dir / r.trace_path, files_to_examine=files_to_examine
                )
            all_trace_grades.append(trace_grade)
            runs.append(
                {
                    "run_number": i,
                    "timestamp": r.timestamp,
                    "outcome": {
                        "success": r.outcome.success,
                        "partial_credit_score": r.outcome.partial_credit_score,
                        "partial_credit_max": r.outcome.partial_credit_max,
                    },
                    "metrics": {
                        "wall_clock_seconds": r.metrics.wall_clock_seconds,
                        "iteration_count": r.metrics.iteration_count,
                        "human_interventions": r.metrics.human_interventions,
                    },
                    "cost": {
                        "input_tokens": r.cost.input_tokens,
                        "output_tokens": r.cost.output_tokens,
                        "estimated_cost_usd": r.cost.estimated_cost_usd,
                    },
                    "quality": {
                        "lint_delta": r.quality.lint_delta,
                        "security_delta": r.quality.security_delta,
                        "test_regressions": r.quality.test_regressions,
                    },
                    "trace_grade": trace_grade,
                }
            )
        submission["results"].append({"task_id": task_id, "runs": runs})

    submission["submission"]["trace_summary"] = _mean_trace_summary(all_trace_grades)
    return submission


@click.command()
@click.argument("run_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default="submission.json", help="Output file")
@click.option("--submitter", default="anonymous", help="Submitter name")
def export(run_dir: str, output: str, submitter: str):
    """Export benchmark results as a shareable submission JSON."""
    import json

    from awb.core.results import ResultRecorder

    recorder = ResultRecorder()
    run_path = Path(run_dir)
    results = recorder.load_run(run_path)
    if not results:
        console.print("[red]No results found[/red]")
        sys.exit(1)

    submission = build_submission(results, run_path, _load_task_defs(), submitter)
    out = Path(output)
    out.write_text(json.dumps(submission, indent=2))
    console.print(f"Exported {len(results)} result(s) to [bold]{out}[/bold]")


@click.command()
@click.argument("file", type=click.Path(exists=True))
def submit(file: str):
    """Validate and display an external submission file."""
    from awb.submission.ingest import load_submission, submission_to_run_results

    try:
        submission = load_submission(Path(file))
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    tool_name = submission.tool.name
    tool_ver = submission.tool.version
    console.print(f"[green]Valid submission[/green]: {tool_name} v{tool_ver}")
    console.print(f"  Model: {submission.model.name} ({submission.model.provider})")
    console.print(f"  Hardware: {submission.environment.hardware_class}")
    console.print(f"  Tasks: {len(submission.results)}")

    results = submission_to_run_results(submission)
    total_runs = len(results)
    passed = sum(1 for r in results if r.outcome.success)
    console.print(f"  Total runs: {total_runs}")
    if results:
        console.print(f"  Pass rate: {passed}/{total_runs} ({passed / total_runs * 100:.0f}%)")


@click.command("compare-submissions")
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
def compare_submissions_cmd(file1: str, file2: str):
    """Compare two external submission files."""
    from awb.submission.compare import compare_submissions
    from awb.submission.ingest import load_submission

    try:
        sub_a = load_submission(Path(file1))
        sub_b = load_submission(Path(file2))
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    comp = compare_submissions(sub_a, sub_b)

    console.print(f"\n[bold]Comparison: {comp.tool_a} vs {comp.tool_b}[/bold]")
    console.print(
        f"  Common tasks: {comp.common_tasks} "
        f"(A has {comp.total_tasks_a}, B has {comp.total_tasks_b})"
    )

    if comp.hardware_warning:
        console.print(f"  [yellow]{comp.hardware_warning}[/yellow]")

    if comp.common_tasks < 5:
        console.print("[yellow]Need 5+ common tasks for meaningful comparison[/yellow]")
        return

    agg_a = comp.scores_a.get("aggregate", 0)
    agg_b = comp.scores_b.get("aggregate", 0)
    console.print(f"\n  {comp.tool_a}: {agg_a:.1f}%")
    console.print(f"  {comp.tool_b}: {agg_b:.1f}%")

    if comp.statistical_comparison:
        sc = comp.statistical_comparison
        sig = "[green]Yes[/green]" if sc.significant else "[yellow]No[/yellow]"
        console.print(f"\n  Statistically significant: {sig}")
        if sc.p_value is not None:
            console.print(f"  p-value: {sc.p_value}")
        console.print(f"  Effect size: {sc.effect_size} ({sc.effect_interpretation})")
        console.print(f"  {sc.message}")

    if comp.per_task:
        table = Table(title="Per-Task Scores")
        table.add_column("Task")
        table.add_column(comp.tool_a, justify="right")
        table.add_column(comp.tool_b, justify="right")
        table.add_column("Delta", justify="right")
        for pt in comp.per_task:
            delta = pt["score_a"] - pt["score_b"]
            delta_str = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
            table.add_row(pt["task_id"], f"{pt['score_a']:.1f}", f"{pt['score_b']:.1f}", delta_str)
        console.print(table)
