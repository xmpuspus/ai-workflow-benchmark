"""run command — executes benchmark tasks through a tool adapter."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import console


def _run_both(
    task_id, category, capability, difficulty, runs, parallel, dry_run, timeout,
    resume=False, concurrency=3, adaptive=False,
):
    """Run vanilla and custom back-to-back then show a comparison."""
    from awb.core.runner import BenchmarkRunner
    from awb.core.task_loader import load_all_tasks

    tasks = load_all_tasks(category=category)
    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
        if not tasks:
            console.print(f"[red]Task '{task_id}' not found[/red]")
            sys.exit(1)
    if capability:
        tasks = [t for t in tasks if capability in t.capabilities]
    if difficulty:
        tasks = [t for t in tasks if t.difficulty == difficulty]

    if not tasks:
        console.print("[yellow]No tasks matched filters[/yellow]")
        return

    if dry_run:
        table = Table(title="Tasks (dry run)")
        table.add_column("ID")
        table.add_column("Title")
        table.add_column("Difficulty")
        table.add_column("Timeout")
        for t in tasks:
            table.add_row(t.id, t.title, t.difficulty, f"{t.constraints.timeout_seconds}s")
        console.print(table)
        return

    all_results = {}
    for variant in ("claude-code-vanilla", "claude-code-custom"):
        console.print(f"\nRunning [bold]{variant}[/bold] on {len(tasks)} task(s) x {runs} run(s)")
        runner = BenchmarkRunner(
            tool=variant, tasks=tasks, runs=runs,
            parallel=parallel, timeout_override=timeout,
            resume=resume, concurrency=concurrency, adaptive=adaptive,
        )
        all_results[variant] = asyncio.run(runner.run_all())

    vanilla_results = all_results["claude-code-vanilla"]
    custom_results = all_results["claude-code-custom"]

    map_v = {r.task_id: r for r in vanilla_results}
    map_c = {r.task_id: r for r in custom_results}
    all_tasks = sorted(set(map_v.keys()) | set(map_c.keys()))

    table = Table(title="Vanilla vs Custom - Side-by-Side")
    table.add_column("Task")
    table.add_column("Vanilla Pass")
    table.add_column("Custom Pass")
    table.add_column("Vanilla Score")
    table.add_column("Custom Score")
    table.add_column("Vanilla Time")
    table.add_column("Custom Time")
    table.add_column("Vanilla Cost")
    table.add_column("Custom Cost")

    for tid in all_tasks:
        rv = map_v.get(tid)
        rc = map_c.get(tid)
        sv = "[green]PASS[/green]" if rv and rv.outcome.success else (
            "[red]FAIL[/red]" if rv else "-")
        sc = "[green]PASS[/green]" if rc and rc.outcome.success else (
            "[red]FAIL[/red]" if rc else "-")
        scv = f"{rv.outcome.partial_credit_score}/{rv.outcome.partial_credit_max}" if rv else "-"
        scc = f"{rc.outcome.partial_credit_score}/{rc.outcome.partial_credit_max}" if rc else "-"
        tv = f"{rv.metrics.wall_clock_seconds:.1f}s" if rv else "-"
        tc = f"{rc.metrics.wall_clock_seconds:.1f}s" if rc else "-"
        cv = f"${rv.cost.estimated_cost_usd:.2f}" if rv else "-"
        cc = f"${rc.cost.estimated_cost_usd:.2f}" if rc else "-"
        table.add_row(tid, sv, sc, scv, scc, tv, tc, cv, cc)

    console.print(table)

    # Workflow Lift Score
    from awb.core.task_loader import load_all_tasks
    from awb.scoring.workflow_lift import compute_workflow_lift

    all_tasks = load_all_tasks()
    task_defs = {t.id: t for t in all_tasks}
    report = compute_workflow_lift(vanilla_results, custom_results, task_defs)

    # Headline
    sig = "[green]significant[/green]" if report.significant else "[yellow]not significant[/yellow]"
    p_str = f"p={report.p_value:.3f}" if report.p_value is not None else "n/a"
    sign = "+" if report.lift >= 0 else ""
    lift_color = "green" if report.lift > 0 else ("red" if report.lift < 0 else "yellow")

    lift_str = f"[{lift_color}]{sign}{report.lift} pts[/{lift_color}]"
    console.print(f"\n[bold]Workflow Lift: {lift_str}[/bold]  ({p_str}, {sig})")
    console.print(
        f"  Pass rate: vanilla {report.vanilla_pass_rate:.0f}%"
        f" vs custom {report.custom_pass_rate:.0f}%"
    )
    console.print(
        f"  Wins: custom {report.custom_wins}"
        f" / vanilla {report.vanilla_wins}"
        f" / ties {report.ties}"
    )

    # Capability breakdown
    helps = [c for c in report.capability_lifts if c.lift > 0.5]
    hurts = [c for c in report.capability_lifts if c.lift < -0.5]

    if helps:
        console.print("\n  [bold]Where your workflow helps:[/bold]")
        for c in helps:
            label = c.capability.replace("_", " ")
            console.print(
                f"    {label:<24} [green]+{c.lift:>5.1f} pts[/green]"
                f"  ({c.tasks} tasks)"
            )

    if hurts:
        console.print("\n  [bold]Where it hurts:[/bold]")
        for c in hurts:
            label = c.capability.replace("_", " ")
            console.print(
                f"    {label:<24} [red]{c.lift:>5.1f} pts[/red]"
                f"  ({c.tasks} tasks)"
            )

    if not helps and not hurts:
        console.print("\n  No significant capability-level differences.")

    # Top movers
    movers = [t for t in report.per_task if abs(t["lift"]) > 5]
    if movers:
        console.print("\n  [bold]Biggest task-level differences:[/bold]")
        for t in movers[:8]:
            sign_t = "+" if t["lift"] > 0 else ""
            color = "green" if t["lift"] > 0 else "red"
            console.print(
                f"    {t['task_id']:<8}"
                f" [{color}]{sign_t}{t['lift']:>5.0f}[/{color}]"
                f"  (V={t['vanilla']:.0f} C={t['custom']:.0f})"
            )


@click.command()
@click.argument("tool", required=False)
@click.option("--workflow", "-w", type=click.Path(exists=True), help="Workflow descriptor YAML")
@click.option("--task", "-t", "task_id", help="Run a single task by ID")
@click.option("--category", "-c", help="Filter tasks by category")
@click.option("--capability", "-cap", help="Filter tasks by capability (e.g., security_awareness)")
@click.option("--difficulty", "-d", help="Filter tasks by difficulty (easy, medium, hard)")
@click.option("--runs", "-n", default=3, help="Number of runs per task")
@click.option("--parallel", is_flag=True, help="Run tasks in parallel")
@click.option("--dry-run", is_flag=True, help="Validate without executing")
@click.option("--timeout", type=int, help="Override timeout (seconds)")
@click.option("--resume", is_flag=True, help="Skip tasks that already have results")
@click.option("-j", "--concurrency", type=int, default=4, help="Max parallel tasks (default: 4)")
@click.option("--adaptive", is_flag=True, help="Only re-run near-miss tasks on runs 2+")
def run(tool: str | None, workflow: str | None, task_id: str | None,
        category: str | None, capability: str | None, difficulty: str | None,
        runs: int, parallel: bool, dry_run: bool, timeout: int | None,
        resume: bool, concurrency: int, adaptive: bool):
    """Run benchmark tasks through a tool adapter."""
    from awb.core.runner import BenchmarkRunner
    from awb.core.task_loader import load_all_tasks

    # Resolve tool from workflow or direct argument
    workflow_info = None
    if workflow:
        from awb.core.config import WorkflowInfo
        from awb.workflow.descriptor import load_descriptor
        descriptor = load_descriptor(Path(workflow))
        tool = descriptor.tool.name
        workflow_info = WorkflowInfo(
            name=descriptor.name,
            descriptor_hash=descriptor.descriptor_hash(),
            tool=descriptor.tool.name,
            model=descriptor.model.name,
            mode=descriptor.mode,
            config_hash=descriptor.config.config_hash,
        )
        console.print(f"Loaded workflow: [bold]{descriptor.name}[/bold]")
    elif not tool:
        # No tool specified - run both variants and compare
        _run_both(task_id=task_id, category=category, capability=capability,
                  difficulty=difficulty, runs=runs, parallel=parallel,
                  dry_run=dry_run, timeout=timeout,
                  resume=resume, concurrency=concurrency, adaptive=adaptive)
        return

    tasks = load_all_tasks(category=category)
    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
        if not tasks:
            console.print(f"[red]Task '{task_id}' not found[/red]")
            sys.exit(1)
    if capability:
        tasks = [t for t in tasks if capability in t.capabilities]
    if difficulty:
        tasks = [t for t in tasks if t.difficulty == difficulty]

    if not tasks:
        console.print("[yellow]No tasks matched filters[/yellow]")
        return

    console.print(f"Running {len(tasks)} task(s) x {runs} run(s) with [bold]{tool}[/bold]")

    # Pre-flight auth check
    from awb.adapters.registry import get_adapter as _get_adapter
    adapter = _get_adapter(tool)
    if adapter.supports_auth_check():
        ok, msg = adapter.check_auth()
        if not ok:
            console.print(f"[red]{msg}[/red]")
            sys.exit(1)

    if dry_run:
        table = Table(title="Tasks (dry run)")
        table.add_column("ID")
        table.add_column("Title")
        table.add_column("Difficulty")
        table.add_column("Timeout")
        for t in tasks:
            table.add_row(t.id, t.title, t.difficulty, f"{t.constraints.timeout_seconds}s")
        console.print(table)
        return

    runner = BenchmarkRunner(
        tool=tool, tasks=tasks, runs=runs,
        parallel=parallel, timeout_override=timeout,
        workflow=workflow_info,
        resume=resume, concurrency=concurrency, adaptive=adaptive,
    )
    results = asyncio.run(runner.run_all())

    # Summary table
    table = Table(title="Results")
    table.add_column("Task")
    table.add_column("Success")
    table.add_column("Score")
    table.add_column("Time (s)")
    table.add_column("Cost ($)")
    table.add_column("Iterations")

    for r in results:
        success_str = "[green]PASS[/green]" if r.outcome.success else "[red]FAIL[/red]"
        score_str = f"{r.outcome.partial_credit_score}/{r.outcome.partial_credit_max}"
        table.add_row(
            r.task_id, success_str, score_str,
            f"{r.metrics.wall_clock_seconds:.1f}",
            f"{r.cost.estimated_cost_usd:.2f}",
            str(r.metrics.iteration_count),
        )

    console.print(table)
    console.print(f"\nResults saved to results/runs/{runner._run_id}*/")
