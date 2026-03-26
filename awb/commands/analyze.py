"""analyze commands — compare, gap, stability."""
from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import console, load_results_from_dirs


@click.command()
@click.argument("run_dir_1", type=click.Path(exists=True))
@click.argument("run_dir_2", type=click.Path(exists=True))
def compare(run_dir_1: str, run_dir_2: str):
    """Compare two benchmark runs side-by-side."""
    from awb.core.results import ResultRecorder

    recorder = ResultRecorder()
    results_1 = recorder.load_run(Path(run_dir_1))
    results_2 = recorder.load_run(Path(run_dir_2))

    if not results_1 or not results_2:
        console.print("[red]One or both run directories are empty[/red]")
        sys.exit(1)

    tool_1 = results_1[0].tool
    tool_2 = results_2[0].tool

    table = Table(title=f"Comparison: {tool_1} vs {tool_2}")
    table.add_column("Task")
    table.add_column(f"{tool_1} Success")
    table.add_column(f"{tool_2} Success")
    table.add_column(f"{tool_1} Score")
    table.add_column(f"{tool_2} Score")
    table.add_column(f"{tool_1} Time")
    table.add_column(f"{tool_2} Time")
    table.add_column(f"{tool_1} Cost")
    table.add_column(f"{tool_2} Cost")

    map_1 = {r.task_id: r for r in results_1}
    map_2 = {r.task_id: r for r in results_2}
    all_tasks = sorted(set(map_1.keys()) | set(map_2.keys()))

    for tid in all_tasks:
        r1 = map_1.get(tid)
        r2 = map_2.get(tid)

        s1 = "[green]PASS[/green]" if r1 and r1.outcome.success else (
            "[red]FAIL[/red]" if r1 else "-")
        s2 = "[green]PASS[/green]" if r2 and r2.outcome.success else (
            "[red]FAIL[/red]" if r2 else "-")
        sc1 = f"{r1.outcome.partial_credit_score}/{r1.outcome.partial_credit_max}" if r1 else "-"
        sc2 = f"{r2.outcome.partial_credit_score}/{r2.outcome.partial_credit_max}" if r2 else "-"
        t1 = f"{r1.metrics.wall_clock_seconds:.1f}s" if r1 else "-"
        t2 = f"{r2.metrics.wall_clock_seconds:.1f}s" if r2 else "-"
        c1 = f"${r1.cost.estimated_cost_usd:.2f}" if r1 else "-"
        c2 = f"${r2.cost.estimated_cost_usd:.2f}" if r2 else "-"

        table.add_row(tid, s1, s2, sc1, sc2, t1, t2, c1, c2)

    console.print(table)


@click.command()
@click.argument("run_dir", type=click.Path(exists=True))
def gap(run_dir: str):
    """Analyze capability gaps and suggest workflow improvements."""
    from awb.analysis.gap_analysis import generate_gap_report
    from awb.core.results import ResultRecorder
    from awb.core.task_loader import load_all_tasks

    recorder = ResultRecorder()
    results = recorder.load_run(Path(run_dir))
    if not results:
        console.print("[red]No results found in directory[/red]")
        sys.exit(1)

    all_tasks = load_all_tasks()
    task_defs = {t.id: t for t in all_tasks}

    report = generate_gap_report(results, task_defs)

    console.print(
        f"\n[bold]{report.tool}[/bold] — Overall: "
        f"[bold cyan]{report.overall_score:.1f}%[/bold cyan]\n"
    )
    console.print("[bold]Capability Profile:[/bold]")
    for cap_name, cap_score in report.capability_profile.scores.items():
        label = cap_name.replace("_", " ")
        if cap_score.score is not None:
            bar_len = int(cap_score.score / 5)
            bar = "=" * bar_len
            pad = " " * (20 - bar_len)
            console.print(
                f"  {label:<24} |{bar}{pad}| "
                f"{cap_score.score:5.1f}  ({cap_score.tasks_tested} tasks)"
            )
        else:
            dots = "." * 20
            console.print(f"  {label:<24} |{dots}|   n/a  (0 tasks)")

    if report.failure_analyses:
        console.print(f"\n[bold]Failures ({len(report.failure_analyses)}):[/bold]")
        for fa in report.failure_analyses:
            console.print(f"\n  [red]{fa.task_id}[/red] - {fa.task_title}")
            console.print(
                f"    Category: {fa.failure_category} | Score: {fa.partial_credit_pct:.0f}%"
            )
            console.print(f"    Capabilities: {', '.join(fa.capabilities_tested)}")
            if fa.criteria_failed:
                console.print(f"    [red]Failed:[/red] {', '.join(fa.criteria_failed)}")
            for s in fa.suggestions[:2]:
                console.print(f"    -> {s}")

    if report.systematic_patterns:
        console.print("\n[bold]Systematic Patterns:[/bold]")
        for p in report.systematic_patterns:
            console.print(f"  - {p}")

    if report.top_improvement_actions:
        console.print("\n[bold]Top Improvement Actions:[/bold]")
        for i, action in enumerate(report.top_improvement_actions, 1):
            console.print(f"  {i}. {action}")


@click.command()
@click.argument("run_dirs", nargs=-1, type=click.Path(exists=True))
def stability(run_dirs: tuple[str, ...]):
    """Analyze per-task score stability across runs."""
    from awb.scoring.statistics import compute_stability_report

    results = load_results_from_dirs(run_dirs)
    if not results:
        console.print("[red]No results found[/red]")
        sys.exit(1)

    report = compute_stability_report(results)
    table = Table(title="Task Stability Report")
    table.add_column("Task")
    table.add_column("Mean", justify="right")
    table.add_column("Std Dev", justify="right")
    table.add_column("Range", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Status")

    for s in report:
        status = "[red]UNSTABLE[/red]" if s.is_unstable else "[green]stable[/green]"
        table.add_row(
            s.task_id,
            f"{s.mean_score:.0f}%",
            f"{s.std_dev:.1f}",
            f"{s.score_range:.0f}",
            str(s.n_runs),
            status,
        )
    console.print(table)

    unstable = [s for s in report if s.is_unstable]
    console.print(f"\n{len(unstable)}/{len(report)} tasks unstable (>30pt range)")
