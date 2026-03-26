"""validate commands — validate, info, quickstart, tools."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import console


@click.command()
@click.option("--task-dir", type=click.Path(exists=True), help="Tasks directory")
def validate(task_dir: str | None):
    """Validate all task YAML files against the schema."""
    from awb.core.config import TASKS_DIR
    from awb.core.task_loader import validate_task_yaml

    tasks_path = Path(task_dir) if task_dir else TASKS_DIR
    task_files = sorted(tasks_path.rglob("*.yaml"))
    task_files = [f for f in task_files if not f.name.startswith("_")]

    if not task_files:
        console.print("[yellow]No task YAML files found[/yellow]")
        return

    errors_found = False
    for path in task_files:
        errors = validate_task_yaml(path)
        rel = path.relative_to(tasks_path)
        if errors:
            errors_found = True
            console.print(f"[red]FAIL[/red] {rel}")
            for e in errors:
                console.print(f"  - {e}")
        else:
            console.print(f"[green]PASS[/green] {rel}")

    if errors_found:
        sys.exit(1)
    else:
        console.print(f"\n[green]All {len(task_files)} tasks valid[/green]")


@click.command()
@click.argument("task_id")
def info(task_id: str):
    """Display details for a specific task."""
    from awb.core.task_loader import load_all_tasks

    tasks = load_all_tasks()
    task = next((t for t in tasks if t.id == task_id), None)
    if not task:
        console.print(f"[red]Task '{task_id}' not found[/red]")
        sys.exit(1)

    console.print(f"\n[bold]{task.id}[/bold] - {task.title}\n")
    console.print(f"  Category:     {task.category}")
    console.print(f"  Difficulty:   {task.difficulty}")
    console.print(
        f"  Time:         {task.estimated_minutes} min"
        f" (timeout: {task.constraints.timeout_seconds}s)"
    )
    console.print(f"  Languages:    {', '.join(task.languages)}")
    console.print(f"  Capabilities: {', '.join(task.capabilities)}")
    console.print(f"  Tags:         {', '.join(task.tags)}")
    console.print(f"  Repo:         {task.repo.url}")
    console.print(f"  Commit:       {task.repo.commit[:12]}")
    console.print(f"  Max iters:    {task.constraints.max_iterations}")

    if task.verification.partial_credit:
        total_pts = sum(c.points for c in task.verification.partial_credit)
        console.print(f"\n  Partial Credit ({total_pts} pts):")
        for c in task.verification.partial_credit:
            console.print(f"    [{c.points:3d}] {c.criterion}")


@click.command()
def quickstart():
    """Run a quick benchmark to verify setup works."""
    from awb.core.runner import BenchmarkRunner
    from awb.core.task_loader import load_all_tasks

    console.print("[bold]AWB Quickstart[/bold] - running BF-001 with vanilla Claude Code\n")

    tasks = load_all_tasks()
    tasks = [t for t in tasks if t.id == "BF-001"]
    if not tasks:
        console.print("[red]Task BF-001 not found[/red]")
        sys.exit(1)

    runner = BenchmarkRunner(
        tool="claude-code-vanilla", tasks=tasks, runs=1, parallel=False,
    )

    try:
        results = asyncio.run(runner.run_all())
    except (OSError, RuntimeError, ValueError) as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if not results:
        console.print("[red]No results produced[/red]")
        sys.exit(1)

    r = results[0]
    status = "[green]PASS[/green]" if r.outcome.success else "[red]FAIL[/red]"
    score = f"{r.outcome.partial_credit_score}/{r.outcome.partial_credit_max}"
    console.print(f"\nResult: {status}")
    console.print(f"Score: {score}")
    console.print(f"Time: {r.metrics.wall_clock_seconds:.1f}s")
    console.print(f"Cost: ${r.cost.estimated_cost_usd:.2f}")
    console.print("\nSetup verified. Run [bold]awb run --runs 1[/bold] for the full 60-task suite.")


@click.command()
def tools():
    """List available tool adapters."""
    from awb.adapters.registry import list_adapters

    table = Table(title="Available Tool Adapters")
    table.add_column("Name")
    table.add_column("Display Name")
    table.add_column("Status")

    for name, display_name, available in list_adapters():
        if available is None:
            status = "[yellow]Stub[/yellow]"
        elif available:
            status = "[green]Available[/green]"
        else:
            status = "[red]Not found[/red]"
        table.add_row(name, display_name, status)

    console.print(table)
