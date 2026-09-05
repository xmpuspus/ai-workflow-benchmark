"""validate commands — validate, info, quickstart, tools."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import console


@click.command()
@click.option("--task-dir", type=click.Path(exists=True), help="Tasks directory")
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Print PASS/FAIL per file. Default is one-line summary.",
)
def validate(task_dir: str | None, verbose: bool):
    """Validate all task YAML files against the schema."""
    from awb.core.config import TASKS_DIR
    from awb.core.task_loader import validate_task_yaml

    tasks_path = Path(task_dir) if task_dir else TASKS_DIR
    task_files = sorted(tasks_path.rglob("*.yaml"))
    task_files = [f for f in task_files if not f.name.startswith("_")]

    if not task_files:
        console.print("[yellow]No task YAML files found[/yellow]")
        return

    failures: list[tuple[Path, list[str]]] = []
    for path in task_files:
        errors = validate_task_yaml(path)
        rel = path.relative_to(tasks_path)
        if errors:
            failures.append((rel, errors))
            if verbose:
                console.print(f"[red]FAIL[/red] {rel}")
                for e in errors:
                    console.print(f"  - {e}")
        elif verbose:
            console.print(f"[green]PASS[/green] {rel}")

    total = len(task_files)
    ok = total - len(failures)
    if failures:
        if not verbose:
            for rel, errors in failures:
                console.print(f"[red]FAIL[/red] {rel}")
                for e in errors:
                    console.print(f"  - {e}")
        console.print(
            f"\n[red]{len(failures)}/{total} failed[/red], [green]{ok}/{total} valid[/green]"
        )
        sys.exit(1)
    else:
        console.print(f"[green]{ok}/{total} tasks valid[/green]")


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
@click.option("--check-auth", is_flag=True, help="Also call installed tool authentication checks.")
def quickstart(check_auth: bool):
    """Verify free local setup; authentication checks require --check-auth."""
    from awb.adapters.registry import list_adapters
    from awb.core.config import RESULTS_DIR
    from awb.core.task_loader import load_all_tasks

    console.print("[bold]AWB Quickstart[/bold] — environment check\n")
    all_ok = True

    # 1. Check tool adapters
    console.print("[bold]1. Tool adapters[/bold]")
    adapters = list_adapters()
    available_count = 0
    for _name, display_name, available in adapters:
        if available is True:
            console.print(f"  [green]OK[/green]  {display_name}")
            available_count += 1
        elif available is None:
            console.print(f"  [yellow]STUB[/yellow] {display_name}")
        else:
            console.print(f"  [red]MISS[/red] {display_name}")
    if available_count == 0:
        console.print("  [red]No adapters available — install at least one tool[/red]")
        all_ok = False

    # 2. Auth checks may invoke an installed CLI, so they are explicitly opt-in.
    console.print("\n[bold]2. Authentication[/bold]")
    if not check_auth:
        console.print(
            "  [dim]Authentication skipped. Re-run with --check-auth to probe installed CLIs.[/dim]"
        )
    else:
        from awb.adapters.registry import get_adapter

        for name, _, available in adapters:
            if available is not True:
                continue
            adapter = get_adapter(name)
            if adapter.supports_auth_check():
                ok, msg = adapter.check_auth()
                status = "[green]OK[/green]" if ok else f"[red]FAIL: {msg}[/red]"
                console.print(f"  {status}  {name}")
                if not ok:
                    all_ok = False
            else:
                console.print(f"  [dim]skip[/dim]  {name} (no auth check)")

    # 3. Load tasks
    console.print("\n[bold]3. Task loading[/bold]")
    try:
        tasks = load_all_tasks()
        console.print(f"  [green]OK[/green]  {len(tasks)} tasks loaded")
    except Exception as e:
        console.print(f"  [red]FAIL[/red]  {e}")
        all_ok = False

    # 4. Results directory writable
    console.print("\n[bold]4. Results directory[/bold]")
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        test_file = RESULTS_DIR / ".quickstart_test"
        test_file.write_text("ok")
        test_file.unlink()
        console.print(f"  [green]OK[/green]  {RESULTS_DIR} (writable)")
    except OSError as e:
        console.print(f"  [red]FAIL[/red]  {RESULTS_DIR}: {e}")
        all_ok = False

    if all_ok:
        console.print(
            "\n[green]Setup verified.[/green] Next, run "
            "[bold]awb checkup --static-only[/bold] for a free local audit."
        )
    else:
        console.print("\n[red]Some checks failed — fix the issues above before running.[/red]")
        sys.exit(1)


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
