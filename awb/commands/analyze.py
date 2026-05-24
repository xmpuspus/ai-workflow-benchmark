"""analyze commands — compare, gap, stability."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import (
    BAD,
    INFO,
    MUTED,
    OK,
    bar,
    confidence_label,
    console,
    emit_json,
    load_results_from_dirs,
    score_style,
)


@click.command()
@click.argument("run_dir_1", type=click.Path(exists=True))
@click.argument("run_dir_2", type=click.Path(exists=True))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the comparison as a JSON document on stdout.",
)
def compare(run_dir_1: str, run_dir_2: str, fmt: str):
    """Compare two benchmark runs side-by-side."""
    from awb.core.results import ResultRecorder

    recorder = ResultRecorder()
    results_1 = recorder.load_run(Path(run_dir_1))
    results_2 = recorder.load_run(Path(run_dir_2))

    if not results_1 or not results_2:
        console.print(f"[{BAD}]One or both run directories are empty[/{BAD}]")
        sys.exit(1)

    tool_1 = results_1[0].tool
    tool_2 = results_2[0].tool

    map_1 = {r.task_id: r for r in results_1}
    map_2 = {r.task_id: r for r in results_2}
    all_tasks = sorted(set(map_1.keys()) | set(map_2.keys()))

    rows: list[dict] = []
    score_diffs: list[float] = []
    for tid in all_tasks:
        r1 = map_1.get(tid)
        r2 = map_2.get(tid)
        sc1 = (
            (r1.outcome.partial_credit_score / max(r1.outcome.partial_credit_max, 1)) * 100
            if r1
            else None
        )
        sc2 = (
            (r2.outcome.partial_credit_score / max(r2.outcome.partial_credit_max, 1)) * 100
            if r2
            else None
        )
        delta = (sc2 - sc1) if (sc1 is not None and sc2 is not None) else None
        if delta is not None:
            score_diffs.append(delta)
        rows.append(
            {
                "task_id": tid,
                "tool_a": tool_1,
                "tool_b": tool_2,
                "pass_a": bool(r1 and r1.outcome.success),
                "pass_b": bool(r2 and r2.outcome.success),
                "score_a": sc1,
                "score_b": sc2,
                "score_delta": delta,
                "time_a": r1.metrics.wall_clock_seconds if r1 else None,
                "time_b": r2.metrics.wall_clock_seconds if r2 else None,
                "cost_a": r1.cost.estimated_cost_usd if r1 else None,
                "cost_b": r2.cost.estimated_cost_usd if r2 else None,
            }
        )

    if fmt == "json":
        emit_json({"tool_a": tool_1, "tool_b": tool_2, "rows": rows})
        return

    table = Table(title=f"{tool_1} vs {tool_2}", header_style="bold")
    table.add_column("Task")
    table.add_column(tool_1)
    table.add_column(tool_2)
    table.add_column("Score Δ", justify="right")
    table.add_column("Time Δ", justify="right")
    table.add_column("Cost Δ", justify="right")
    for row in rows:
        s1 = f"[{OK}]PASS[/{OK}]" if row["pass_a"] else f"[{BAD}]FAIL[/{BAD}]"
        s2 = f"[{OK}]PASS[/{OK}]" if row["pass_b"] else f"[{BAD}]FAIL[/{BAD}]"
        delta = row["score_delta"]
        delta_str = (
            "-"
            if delta is None
            else f"[{OK}]+{delta:.0f}[/{OK}]"
            if delta > 0
            else f"[{BAD}]{delta:.0f}[/{BAD}]"
            if delta < 0
            else f"[{MUTED}]0[/{MUTED}]"
        )
        time_a, time_b = row["time_a"], row["time_b"]
        time_delta = "-" if time_a is None or time_b is None else f"{time_b - time_a:+.0f}s"
        cost_a, cost_b = row["cost_a"], row["cost_b"]
        cost_delta = "-" if cost_a is None or cost_b is None else f"${cost_b - cost_a:+.2f}"
        table.add_row(row["task_id"], s1, s2, delta_str, time_delta, cost_delta)
    console.print(table)
    if score_diffs:
        mean_delta = sum(score_diffs) / len(score_diffs)
        wins = sum(1 for d in score_diffs if d > 0)
        losses = sum(1 for d in score_diffs if d < 0)
        ties = sum(1 for d in score_diffs if d == 0)
        mean_str = (
            f"[{OK}]+{mean_delta:.1f}[/{OK}]"
            if mean_delta > 0
            else f"[{BAD}]{mean_delta:.1f}[/{BAD}]"
            if mean_delta < 0
            else f"[{MUTED}]0.0[/{MUTED}]"
        )
        console.print(
            f"\nMean score Δ: {mean_str}  "
            f"wins {wins} / losses {losses} / ties {ties}  (n={len(score_diffs)})"
        )


@click.command()
@click.argument("run_dir", type=click.Path(exists=True))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the GapReport as a JSON document on stdout.",
)
def gap(run_dir: str, fmt: str):
    """Analyze capability gaps and suggest workflow improvements."""
    from awb.analysis.gap_analysis import generate_gap_report
    from awb.core.results import ResultRecorder
    from awb.core.task_loader import load_all_tasks

    recorder = ResultRecorder()
    results = recorder.load_run(Path(run_dir))
    if not results:
        console.print(f"[{BAD}]No results found in directory[/{BAD}]")
        sys.exit(1)

    all_tasks = load_all_tasks()
    task_defs = {t.id: t for t in all_tasks}
    report = generate_gap_report(results, task_defs)

    if fmt == "json":
        emit_json(report)
        return

    overall_style = score_style(report.overall_score)
    console.print(
        f"\n[bold]{report.tool}[/bold]  Overall: "
        f"[bold {overall_style}]{report.overall_score:.1f}[/bold {overall_style}]\n"
    )
    console.print("[bold]Capability Profile[/bold]")
    for cap_name, cap_score in report.capability_profile.scores.items():
        label = cap_name.replace("_", " ")
        n = cap_score.tasks_tested
        if cap_score.score is not None:
            style = score_style(cap_score.score)
            conf = confidence_label(n)
            console.print(
                f"  {label:<24} [{style}]{bar(cap_score.score)}[/{style}]  "
                f"{cap_score.score:5.1f}  ({n:>2}, conf={conf})"
            )
        else:
            console.print(f"  {label:<24} [{MUTED}]{bar(None)}[/{MUTED}]   n/a   (0 tasks)")

    if report.failure_analyses:
        console.print(f"\n[bold]Failures ({len(report.failure_analyses)})[/bold]")
        for fa in report.failure_analyses:
            console.print(f"\n  [{BAD}]{fa.task_id}[/{BAD}]  {fa.task_title}")
            console.print(
                f"    Category: {fa.failure_category}  Score: {fa.partial_credit_pct:.0f}%"
            )
            console.print(f"    Capabilities: {', '.join(fa.capabilities_tested)}")
            if fa.criteria_failed:
                console.print(f"    [{BAD}]Failed:[/{BAD}] {', '.join(fa.criteria_failed)}")
            for s in fa.suggestions[:2]:
                console.print(f"    [{INFO}]->[/{INFO}] {s}")

    if report.systematic_patterns:
        console.print("\n[bold]Systematic Patterns[/bold]")
        for p in report.systematic_patterns:
            console.print(f"  - {p}")

    if report.top_improvement_actions:
        console.print("\n[bold]Top Suggestions[/bold]")
        for i, action in enumerate(report.top_improvement_actions, 1):
            console.print(f"  {i}. {action}")


@click.command()
@click.argument("run_dirs", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the stability report as a JSON array on stdout.",
)
def stability(run_dirs: tuple[str, ...], fmt: str):
    """Analyze per-task score stability across runs."""
    from awb.scoring.statistics import compute_stability_report

    results = load_results_from_dirs(run_dirs)
    if not results:
        console.print(f"[{BAD}]No results found[/{BAD}]")
        sys.exit(1)

    report = compute_stability_report(results)

    if fmt == "json":
        emit_json(report)
        return

    table = Table(title="Task Stability", header_style="bold")
    table.add_column("Task")
    table.add_column("Mean", justify="right")
    table.add_column("Std Dev", justify="right")
    table.add_column("Range", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Status")
    for s in report:
        status = f"[{BAD}]UNSTABLE[/{BAD}]" if s.is_unstable else f"[{OK}]stable[/{OK}]"
        table.add_row(
            s.task_id,
            f"{s.mean_score:.0f}",
            f"{s.std_dev:.1f}",
            f"{s.score_range:.0f}",
            str(s.n_runs),
            status,
        )
    console.print(table)
    unstable = [s for s in report if s.is_unstable]
    console.print(f"\n{len(unstable)}/{len(report)} tasks unstable (>30pt range)")
