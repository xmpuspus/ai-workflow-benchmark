"""calibrate commands — difficulty and timeout recalibration."""
from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import console, load_results_from_dirs


@click.command("calibrate-difficulty")
@click.argument("run_dirs", nargs=-1, type=click.Path(exists=True))
@click.option("--apply", is_flag=True, help="Update task YAML files")
def calibrate_difficulty_cmd(run_dirs: tuple[str, ...], apply: bool):
    """Recalibrate difficulty labels using empirical pass rates."""
    from awb.analysis.difficulty_calibrator import (
        apply_difficulty_labels,
        calibrate_difficulty,
    )

    results = load_results_from_dirs(run_dirs)
    if not results:
        console.print("[red]No results found[/red]")
        sys.exit(1)

    recs = calibrate_difficulty(results)
    table = Table(title="Difficulty Calibration")
    table.add_column("Task")
    table.add_column("Current")
    table.add_column("Recommended")
    table.add_column("Pass Rate", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Changed")

    for r in recs:
        changed = "[yellow]YES[/yellow]" if r.changed else ""
        table.add_row(
            r.task_id, r.current, r.recommended,
            f"{r.pass_rate:.0f}%", str(r.n_runs), changed,
        )
    console.print(table)

    changes = [r for r in recs if r.changed]
    console.print(f"\n{len(changes)}/{len(recs)} tasks would change difficulty")

    if apply and changes:
        tasks_dir = Path(__file__).parent.parent / "tasks"
        count = apply_difficulty_labels(recs, tasks_dir)
        console.print(f"[green]Updated {count} task files[/green]")


@click.command("calibrate-timeouts")
@click.argument("run_dirs", nargs=-1, type=click.Path(exists=True))
@click.option("--apply", is_flag=True, help="Update task YAML files")
def calibrate_timeouts_cmd(run_dirs: tuple[str, ...], apply: bool):
    """Calibrate task timeouts using empirical wall clock data."""
    from awb.analysis.timeout_calibrator import (
        apply_timeouts,
        calibrate_timeouts,
    )

    results = load_results_from_dirs(run_dirs)
    if not results:
        console.print("[red]No results found[/red]")
        sys.exit(1)

    recs = calibrate_timeouts(results)
    table = Table(title="Timeout Calibration")
    table.add_column("Task")
    table.add_column("Current", justify="right")
    table.add_column("p95 Time", justify="right")
    table.add_column("Recommended", justify="right")
    table.add_column("Changed")

    for r in recs:
        changed = "[yellow]YES[/yellow]" if r.changed else ""
        table.add_row(
            r.task_id, f"{r.current_timeout}s",
            f"{r.p95_time:.0f}s", f"{r.recommended_timeout}s", changed,
        )
    console.print(table)

    changes = [r for r in recs if r.changed]
    console.print(f"\n{len(changes)}/{len(recs)} tasks would change timeout")

    if apply and changes:
        tasks_dir = Path(__file__).parent.parent / "tasks"
        count = apply_timeouts(recs, tasks_dir)
        console.print(f"[green]Updated {count} task files[/green]")
