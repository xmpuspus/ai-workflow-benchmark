"""CLI interface for the AI Workflow Benchmark."""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from awb import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="awb")
def cli():
    """AI Workflow Benchmark - measure tool+workflow performance."""
    pass


def _run_both(task_id, category, capability, difficulty, runs, parallel, dry_run, timeout):
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

    # Summary line
    total_v = sum(r.outcome.partial_credit_score for r in vanilla_results)
    max_v = sum(r.outcome.partial_credit_max for r in vanilla_results)
    total_c = sum(r.outcome.partial_credit_score for r in custom_results)
    max_c = sum(r.outcome.partial_credit_max for r in custom_results)

    pct_v = (total_v / max_v * 100) if max_v else 0
    pct_c = (total_c / max_c * 100) if max_c else 0
    delta = pct_c - pct_v

    if delta > 0:
        summary = (
            f"Your workflow scored {pct_c:.0f}% vs vanilla {pct_v:.0f}%"
            f" - that's a +{delta:.0f}% improvement"
        )
    elif delta < 0:
        summary = (
            f"Your workflow scored {pct_c:.0f}% vs vanilla {pct_v:.0f}%"
            f" - vanilla leads by {-delta:.0f}%"
        )
    else:
        summary = f"Your workflow scored {pct_c:.0f}% - tied with vanilla"

    console.print(f"\n[bold]{summary}[/bold]")


@cli.command()
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
def run(tool: str | None, workflow: str | None, task_id: str | None,
        category: str | None, capability: str | None, difficulty: str | None,
        runs: int, parallel: bool, dry_run: bool, timeout: int | None):
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
                  dry_run=dry_run, timeout=timeout)
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


@cli.command()
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


@cli.command()
@click.argument("run_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default="submission.json", help="Output file")
@click.option("--submitter", default="anonymous", help="Submitter name")
def export(run_dir: str, output: str, submitter: str):
    """Export benchmark results as a shareable submission JSON."""
    import json
    from datetime import datetime

    from awb import __version__
    from awb.core.results import ResultRecorder

    recorder = ResultRecorder()
    results = recorder.load_run(Path(run_dir))
    if not results:
        console.print("[red]No results found[/red]")
        sys.exit(1)

    by_task: dict = {}
    for r in results:
        if r.task_id not in by_task:
            by_task[r.task_id] = []
        by_task[r.task_id].append(r)

    submission = {
        "spec_version": "awb/v2",
        "submission": {
            "submitter": submitter,
            "submitted_at": datetime.now(UTC).isoformat(),
            "tool": {
                "name": results[0].tool,
                "version": results[0].tool_version,
            },
            "model": {
                "name": results[0].model or "unknown",
            },
            "environment": {
                "os": results[0].environment.os,
                "hardware_class": "other",
                "hardware_detail": results[0].environment.hardware,
            },
            "awb_version": __version__,
        },
        "results": [],
    }

    for task_id, task_results in sorted(by_task.items()):
        runs = []
        for i, r in enumerate(task_results, 1):
            runs.append({
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
            })
        submission["results"].append({"task_id": task_id, "runs": runs})

    out = Path(output)
    out.write_text(json.dumps(submission, indent=2))
    console.print(f"Exported {len(results)} result(s) to [bold]{out}[/bold]")


@cli.command()
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
    except Exception as e:
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


@cli.command()
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


@cli.command()
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


@cli.command()
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


@cli.command("compare-submissions")
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


@cli.command()
@click.option("--output-dir", type=click.Path(), help="Output directory")
def leaderboard(output_dir: str | None):
    """Generate HTML leaderboard from results."""
    from awb.leaderboard.generate import generate_leaderboard

    out = Path(output_dir) if output_dir else None
    path = generate_leaderboard(output_dir=out)
    console.print(f"Leaderboard generated: [bold]{path}[/bold]")


@cli.command()
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


@cli.command()
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


# --- Workflow command group ---

@cli.group()
def workflow():
    """Manage workflow descriptors."""
    pass


@workflow.command("export")
@click.argument("tool")
@click.option("--name", "-n", required=True, help="Workflow name")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def workflow_export(tool: str, name: str, output: str | None):
    """Generate a workflow descriptor YAML from current tool config."""
    from awb.workflow.exporter import export_workflow

    out = Path(output) if output else None
    path = export_workflow(tool, name, output_path=out)
    console.print(f"Workflow exported: [bold]{path}[/bold]")


@workflow.command("validate")
@click.argument("file", type=click.Path(exists=True))
def workflow_validate(file: str):
    """Validate a workflow descriptor YAML."""
    from awb.workflow.descriptor import validate_descriptor

    errors = validate_descriptor(Path(file))
    if errors:
        console.print(f"[red]FAIL[/red] {file}")
        for e in errors:
            console.print(f"  - {e}")
        sys.exit(1)
    else:
        console.print(f"[green]PASS[/green] {file}")


@workflow.command("diff")
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
def workflow_diff(file1: str, file2: str):
    """Compare two workflow descriptors."""
    from awb.workflow.descriptor import load_descriptor

    d1 = load_descriptor(Path(file1))
    d2 = load_descriptor(Path(file2))

    table = Table(title=f"Workflow Diff: {d1.name} vs {d2.name}")
    table.add_column("Field")
    table.add_column(d1.name)
    table.add_column(d2.name)
    table.add_column("Match")

    comparisons = [
        ("tool", d1.tool.name, d2.tool.name),
        ("mode", d1.mode, d2.mode),
        ("model", d1.model.name, d2.model.name),
        ("max_turns", str(d1.config.max_turns), str(d2.config.max_turns)),
        ("timeout", str(d1.config.timeout_seconds), str(d2.config.timeout_seconds)),
        ("config_hash", d1.config.config_hash, d2.config.config_hash),
        ("hooks", str(d1.environment.hooks_count), str(d2.environment.hooks_count)),
        ("agents", str(d1.environment.agents_count), str(d2.environment.agents_count)),
        ("skills", str(d1.environment.skills_count), str(d2.environment.skills_count)),
        ("descriptor_hash", d1.descriptor_hash(), d2.descriptor_hash()),
    ]

    for field, v1, v2 in comparisons:
        match = "[green]=[/green]" if v1 == v2 else "[red]!=[/red]"
        table.add_row(field, v1, v2, match)

    console.print(table)


@workflow.command("init")
@click.option("--output", "-o", type=click.Path(), default="workflow.yaml", help="Output file")
def workflow_init(output: str):
    """Interactively create a workflow descriptor."""
    from awb.adapters.registry import list_adapters

    adapters = list_adapters()
    adapter_names = [a[0] for a in adapters]

    console.print("[bold]Create a new workflow descriptor[/bold]\n")
    name = click.prompt("Workflow name")
    tool = click.prompt("Tool", type=click.Choice(adapter_names))
    model = click.prompt("Model (optional)", default="")
    max_turns = click.prompt("Max turns", default=20, type=int)
    timeout_s = click.prompt("Timeout (seconds)", default=1800, type=int)

    import yaml

    from awb.workflow.exporter import export_claude_code_config

    descriptor = {
        "spec": "awb/v1",
        "name": name,
        "tool": tool,
        "mode": "custom" if tool == "claude-code-custom" else "vanilla",
        "config": {
            "max_turns": max_turns,
            "timeout_seconds": timeout_s,
        },
    }
    if model:
        descriptor["model"] = model
    if tool == "claude-code-custom":
        descriptor["environment"] = export_claude_code_config()

    out = Path(output)
    out.write_text(yaml.dump(descriptor, default_flow_style=False, sort_keys=False))
    console.print(f"\nWorkflow created: [bold]{out}[/bold]")
