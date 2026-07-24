"""run command, executes benchmark tasks through a tool adapter."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import BAD, console


def _score_style(score: float) -> str:
    """Return Rich style for score band."""
    if score >= 80:
        return "green"
    elif score >= 50:
        return "yellow"
    return "red"


def _run_both(
    task_id,
    category,
    capability,
    difficulty,
    runs,
    parallel,
    dry_run,
    timeout,
    resume=False,
    concurrency=3,
    adaptive=False,
    tasks_dir=None,
    progressive=False,
    fast_check=False,
    use_uv=False,
    yes=False,
):
    """Run vanilla and custom back-to-back then show a comparison."""
    from awb.core.runner import BenchmarkRunner
    from awb.core.task_loader import load_all_tasks

    tasks = load_all_tasks(tasks_dir=tasks_dir, category=category)
    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
        if not tasks:
            console.print(f"[red]Task '{task_id}' not found[/red]")
            sys.exit(1)
    if capability:
        tasks = [t for t in tasks if capability in t.capabilities]
    if difficulty:
        tasks = [t for t in tasks if t.difficulty == difficulty]

    # Fast-check mode: select representative tasks once, before the variant
    # loop, so both variants run the identical 8 tasks (mirrors the
    # tool-specified path below; see run.py:291-299 in the original bug).
    if fast_check:
        from awb.core.fast_check import select_fast_check_tasks

        tasks = select_fast_check_tasks(tasks)
        runs = 1  # Single run for fast-check
        console.print(
            f"[bold cyan]Fast-check mode:[/bold cyan] {len(tasks)} representative tasks, 1 run"
        )

    if not tasks:
        console.print("[yellow]No tasks matched filters[/yellow]")
        return

    # Confirmation prompt for large runs (same threshold as the tool-specified
    # path; fast-check's 8 tasks x 1 run stays under it). Cost is doubled
    # here since both variants actually execute the task set.
    total_runs = len(tasks) * runs
    est_cost = total_runs * 0.50 * 2  # rough estimate: ~$0.50/task, x2 variants
    if not yes and not task_id and total_runs > 10:
        console.print(
            f"About to run [bold]{len(tasks)}[/bold] task(s) x "
            f"[bold]{runs}[/bold] run(s) x 2 variants = "
            f"[bold]{total_runs * 2}[/bold] executions "
            f"(estimated ~${est_cost:.0f})"
        )
        if not click.confirm("Proceed?", default=True):
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

    # Pre-flight availability + auth check for both variants before any
    # workspace prep, so a missing auth fails in 1s instead of after a clone.
    from awb.adapters.registry import get_adapter as _get_adapter

    for variant in ("claude-code-vanilla", "claude-code-custom"):
        adapter = _get_adapter(variant)
        try:
            if not adapter.check_available():
                console.print(
                    f"[red]Adapter '{variant}' is not available in this environment[/red]"
                )
                sys.exit(1)
        except NotImplementedError as exc:
            raise click.UsageError(
                f"Adapter '{variant}' is a stub, not yet implemented. "
                f"Run 'awb tools' to see available adapters."
            ) from exc

        if adapter.supports_auth_check():
            ok, msg = adapter.check_auth()
            if not ok:
                console.print(f"[red]{msg}[/red]")
                sys.exit(1)

    all_results = {}
    runners = {}
    for variant in ("claude-code-vanilla", "claude-code-custom"):
        console.print(f"\nRunning [bold]{variant}[/bold] on {len(tasks)} task(s) x {runs} run(s)")
        runner = BenchmarkRunner(
            tool=variant,
            tasks=tasks,
            runs=runs,
            parallel=parallel,
            timeout_override=timeout,
            resume=resume,
            concurrency=concurrency,
            adaptive=adaptive,
            progressive=progressive,
            use_uv=use_uv,
            tasks_dir=tasks_dir,
        )
        all_results[variant] = asyncio.run(runner.run_all())
        runners[variant] = runner

    vanilla_results = all_results["claude-code-vanilla"]
    custom_results = all_results["claude-code-custom"]

    # Record the custom variant's run dir for --last-run consumers (gap,
    # cost, drift, trace grade) - mirrors the tool-specified path below and
    # checkup --paired, which likewise saves the custom arm, not the vanilla.
    custom_runner = runners["claude-code-custom"]
    results_path = custom_runner.recorder.results_dir
    run_dirs = sorted(results_path.glob(f"{custom_runner._run_id}_run*"))
    if run_dirs:
        from awb.commands._shared import save_last_run

        save_last_run(run_dirs[0])

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
        sv = (
            "[green]PASS[/green]"
            if rv and rv.outcome.success
            else ("[red]FAIL[/red]" if rv else "-")
        )
        sc = (
            "[green]PASS[/green]"
            if rc and rc.outcome.success
            else ("[red]FAIL[/red]" if rc else "-")
        )
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

    all_tasks = load_all_tasks(tasks_dir=tasks_dir)
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
        f"  Wins: custom {report.custom_wins} / vanilla {report.vanilla_wins} / ties {report.ties}"
    )

    # Capability breakdown
    helps = [c for c in report.capability_lifts if c.lift > 0.5]
    hurts = [c for c in report.capability_lifts if c.lift < -0.5]

    if helps:
        console.print("\n  [bold]Where your workflow helps:[/bold]")
        for c in helps:
            label = c.capability.replace("_", " ")
            console.print(f"    {label:<24} [green]+{c.lift:>5.1f} pts[/green]  ({c.tasks} tasks)")

    if hurts:
        console.print("\n  [bold]Where it hurts:[/bold]")
        for c in hurts:
            label = c.capability.replace("_", " ")
            console.print(f"    {label:<24} [red]{c.lift:>5.1f} pts[/red]  ({c.tasks} tasks)")

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
@click.option("--parallel", is_flag=True, help="Run tasks in parallel (fans out to 4 by default)")
@click.option("--dry-run", is_flag=True, help="Validate without executing")
@click.option("--timeout", type=int, help="Override timeout (seconds)")
@click.option("--resume", is_flag=True, help="Skip tasks that already have results")
@click.option(
    "-j",
    "--concurrency",
    type=int,
    default=None,
    help="Max parallel tasks; -j>1 enables parallel mode (default: 1 sequential, "
    "4 with --fast-check)",
)
@click.option("--adaptive", is_flag=True, help="Only re-run near-miss tasks on runs 2+")
@click.option("--progressive", is_flag=True, help="Run easy first, stop early if failing")
@click.option("--fast-check", is_flag=True, help="Run 8 representative tasks for quick signal")
@click.option("--use-uv", is_flag=True, help="Use uv instead of pip for faster installs")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option(
    "--tasks-dir",
    type=click.Path(exists=True),
    help="Load tasks from a custom directory (e.g. private tasks) instead of the packaged ones",
)
def run(
    tool: str | None,
    workflow: str | None,
    task_id: str | None,
    category: str | None,
    capability: str | None,
    difficulty: str | None,
    runs: int,
    parallel: bool,
    dry_run: bool,
    timeout: int | None,
    resume: bool,
    concurrency: int | None,
    adaptive: bool,
    progressive: bool,
    fast_check: bool,
    use_uv: bool,
    yes: bool,
    tasks_dir: str | None,
):
    """Run benchmark tasks through a tool adapter."""
    from awb.core.runner import BenchmarkRunner
    from awb.core.task_loader import load_all_tasks

    tasks_dir_path = Path(tasks_dir) if tasks_dir else None

    # Resume matches an incomplete run by tool + task count only; mined
    # private tasks reuse public ID prefixes (BF-001...), so resuming across
    # task sets would silently fold cached public results into a private run.
    if tasks_dir_path and resume:
        console.print(f"[{BAD}]--resume cannot be combined with --tasks-dir yet[/{BAD}]")
        console.print("Run the private task set without --resume.")
        sys.exit(1)

    # Fast-check defaults to parallel at concurrency 4, the empirically safe
    # sweet spot (git clones start failing above it). An explicit -j always
    # wins, including -j 1 to force sequential; non-fast-check behavior is
    # unchanged (sequential, concurrency 1, unless -j/--parallel says otherwise).
    concurrency_explicit = concurrency is not None
    if concurrency is None:
        concurrency = 4 if fast_check else 1
    if fast_check and not (concurrency_explicit and concurrency <= 1):
        parallel = True

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
        _run_both(
            task_id=task_id,
            category=category,
            capability=capability,
            difficulty=difficulty,
            runs=runs,
            parallel=parallel,
            dry_run=dry_run,
            timeout=timeout,
            resume=resume,
            concurrency=concurrency,
            adaptive=adaptive,
            tasks_dir=tasks_dir_path,
            progressive=progressive,
            fast_check=fast_check,
            use_uv=use_uv,
            yes=yes,
        )
        return

    tasks = load_all_tasks(tasks_dir=tasks_dir_path, category=category)
    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
        if not tasks:
            console.print(f"[red]Task '{task_id}' not found[/red]")
            sys.exit(1)
    if capability:
        tasks = [t for t in tasks if capability in t.capabilities]
    if difficulty:
        tasks = [t for t in tasks if t.difficulty == difficulty]

    # Fast-check mode: select representative tasks
    if fast_check:
        from awb.core.fast_check import select_fast_check_tasks

        tasks = select_fast_check_tasks(tasks)
        runs = 1  # Single run for fast-check
        console.print(
            f"[bold cyan]Fast-check mode:[/bold cyan] {len(tasks)} representative tasks, 1 run"
        )

    if not tasks:
        console.print("[yellow]No tasks matched filters[/yellow]")
        return

    # Confirmation prompt for large runs
    total_runs = len(tasks) * runs
    est_cost = total_runs * 0.50  # rough estimate: ~$0.50/task
    if not yes and not task_id and total_runs > 10:
        console.print(
            f"About to run [bold]{len(tasks)}[/bold] task(s) x "
            f"[bold]{runs}[/bold] run(s) = [bold]{total_runs}[/bold] executions "
            f"(estimated ~${est_cost:.0f})"
        )
        if not click.confirm("Proceed?", default=True):
            return

    console.print(f"Running {len(tasks)} task(s) x {runs} run(s) with [bold]{tool}[/bold]")

    # Dry run is a pure preview of the selected tasks; it must not pay the
    # adapter preflight (check_auth makes a real model call, up to 30s).
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

    # Pre-flight availability + auth check
    from awb.adapters.registry import get_adapter as _get_adapter

    adapter = _get_adapter(tool)
    try:
        if not adapter.check_available():
            console.print(f"[red]Adapter '{tool}' is not available in this environment[/red]")
            sys.exit(1)
    except NotImplementedError as exc:
        raise click.UsageError(
            f"Adapter '{tool}' is a stub, not yet implemented. "
            f"Run 'awb tools' to see available adapters."
        ) from exc

    if adapter.supports_auth_check():
        ok, msg = adapter.check_auth()
        if not ok:
            console.print(f"[red]{msg}[/red]")
            sys.exit(1)

    runner = BenchmarkRunner(
        tool=tool,
        tasks=tasks,
        runs=runs,
        parallel=parallel,
        timeout_override=timeout,
        workflow=workflow_info,
        resume=resume,
        concurrency=concurrency,
        adaptive=adaptive,
        progressive=progressive,
        use_uv=use_uv,
        tasks_dir=tasks_dir_path,
    )
    try:
        results = asyncio.run(runner.run_all())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted, partial results saved[/yellow]")
        return

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
        max_pts = r.outcome.partial_credit_max or 1
        pct = (r.outcome.partial_credit_score / max_pts) * 100
        color = _score_style(pct)
        score_str = (
            f"[{color}]{r.outcome.partial_credit_score}/{r.outcome.partial_credit_max}[/{color}]"
        )
        table.add_row(
            r.task_id,
            success_str,
            score_str,
            f"{r.metrics.wall_clock_seconds:.1f}",
            f"{r.cost.estimated_cost_usd:.2f}",
            str(r.metrics.iteration_count),
        )

    console.print(table)

    # Fast-check estimate
    if fast_check:
        from awb.core.fast_check import estimate_full_score

        fast_data = [
            {
                "partial_credit_score": r.outcome.partial_credit_score,
                "partial_credit_max": r.outcome.partial_credit_max,
            }
            for r in results
        ]
        est, margin = estimate_full_score(fast_data)
        console.print(f"\n[bold]Estimated full-suite score: {est:.0f} +/- {margin:.0f}[/bold]")

    # Integrity checks
    from awb.scoring.integrity import run_integrity_checks

    warnings = run_integrity_checks(results)
    if warnings:
        console.print(f"\n[bold yellow]Integrity warnings ({len(warnings)}):[/bold yellow]")
        for w in warnings:
            severity_style = "red" if w.severity == "critical" else "yellow"
            console.print(
                f"  [{severity_style}][{w.severity.upper()}][/{severity_style}]"
                f" {w.task_id}: {w.message}"
            )

    results_path = runner.recorder.results_dir
    run_dirs = sorted(results_path.glob(f"{runner._run_id}_run*"))
    if run_dirs:
        from awb.commands._shared import save_last_run

        save_last_run(run_dirs[0])
        console.print(f"\nResults saved to {run_dirs[0].parent}/{runner._run_id}_run*/")
    else:
        console.print(f"\nResults saved to {results_path}/{runner._run_id}/")
