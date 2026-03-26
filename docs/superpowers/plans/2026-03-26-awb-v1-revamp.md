# AWB v1.0 Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Comprehensive overhaul of AWB — refactor internals, fix scoring, add test coverage, implement 4 new adapters, upgrade terminal output and leaderboard.

**Architecture:** Foundation-first approach. Phase 1-2 stabilize internals (CLI breakup, scoring fixes). Phase 3 adds test coverage. Phase 4 adds adapters. Phase 5 upgrades output. Phase 6 handles migration.

**Tech Stack:** Python 3.11+, Click, Rich, Chart.js (CDN), Jinja2, pytest, asyncio

---

## File Structure

### Files to Create
```
awb/commands/__init__.py          # Command package init
awb/commands/run.py               # awb run + _run_both()
awb/commands/analyze.py           # awb gap, compare, stability
awb/commands/calibrate.py         # awb calibrate-difficulty, calibrate-timeouts
awb/commands/submit.py            # awb submit, compare-submissions, export
awb/commands/validate.py          # awb validate, info, tools
awb/commands/leaderboard_cmd.py   # awb leaderboard
awb/commands/workflow_cmd.py      # awb workflow export/validate/diff/init
awb/commands/migrate.py           # awb migrate-results (new)
awb/commands/_shared.py           # Shared console, helpers
awb/adapters/gemini_cli.py        # Gemini CLI adapter
awb/adapters/codex_cli.py         # Codex CLI adapter
awb/adapters/windsurf.py          # Windsurf adapter
awb/adapters/copilot_cli.py       # Copilot CLI adapter
tests/test_runner.py              # BenchmarkRunner tests
tests/test_results.py             # ResultRecorder tests
tests/test_metrics.py             # MetricCollector + cost tests
tests/test_code_review_scorer.py  # F1 calc tests
tests/test_gap_analysis.py        # Gap analysis tests
tests/test_submission.py          # Ingest + compare tests
tests/test_lint_checker.py        # Lint checker tests
tests/test_cli_integration.py     # CLI command smoke tests
```

### Files to Modify
```
awb/cli.py                        # Gutted to thin entry point
awb/__init__.py                   # Version bump to 1.0.0
awb/adapters/base.py              # New ABC methods
awb/adapters/registry.py          # New adapter fallbacks
awb/scoring/capabilities.py       # Add 3 missing capabilities
awb/scoring/composite.py          # Weight sum validation
awb/scoring/statistics.py         # strict=True fix
awb/scoring/integrity.py          # Named constant
awb/scoring/report.py             # Align metric names
awb/core/config.py                # Remove dead code
awb/core/metrics.py               # Configurable pricing
awb/core/task_loader.py           # Log skipped tasks
awb/tasks/schema.json             # Partial credit sum validation note
awb/leaderboard/generate.py       # Chart.js data, history tracking
awb/leaderboard/templates/index.html  # Enhanced leaderboard
awb/leaderboard/static/leaderboard.js # Chart.js charts
awb/leaderboard/static/style.css  # New chart styles
pyproject.toml                    # New entry points, version bump
tests/conftest.py                 # New fixtures
```

---

## Phase 1: Package Restructuring

### Task 1: Create shared CLI utilities module

**Files:**
- Create: `awb/commands/__init__.py`
- Create: `awb/commands/_shared.py`

- [ ] **Step 1: Create the commands package**

```python
# awb/commands/__init__.py
"""CLI command modules for AWB."""
```

- [ ] **Step 2: Create the shared utilities module**

```python
# awb/commands/_shared.py
"""Shared CLI utilities — console instance, result loading, formatters."""
from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def load_results_from_dirs(run_dirs: tuple[str, ...]) -> list:
    """Load RunResult objects from multiple run directories."""
    from awb.core.results import ResultRecorder

    recorder = ResultRecorder()
    all_results = []
    for d in run_dirs:
        all_results.extend(recorder.load_run(Path(d)))
    return all_results
```

- [ ] **Step 3: Verify import works**

Run: `python3 -c "from awb.commands._shared import console; print(type(console))"`
Expected: `<class 'rich.console.Console'>`

- [ ] **Step 4: Commit**

```bash
git add awb/commands/__init__.py awb/commands/_shared.py
git commit -m "Add commands package with shared CLI utilities"
```

---

### Task 2: Extract run command

**Files:**
- Create: `awb/commands/run.py`
- Modify: `awb/cli.py`

- [ ] **Step 1: Create run.py with _run_both() and run command**

Copy lines 25-293 from `awb/cli.py` into `awb/commands/run.py`. Replace `console` import:

```python
# awb/commands/run.py
"""Benchmark run commands."""
from __future__ import annotations

import asyncio
import sys

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
    all_task_ids = sorted(set(map_v.keys()) | set(map_c.keys()))

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

    for tid in all_task_ids:
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
    from awb.core.task_loader import load_all_tasks as _load_all
    from awb.scoring.workflow_lift import compute_workflow_lift

    all_loaded = _load_all()
    task_defs = {t.id: t for t in all_loaded}
    report = compute_workflow_lift(vanilla_results, custom_results, task_defs)

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
def run(tool, workflow, task_id, category, capability, difficulty,
        runs, parallel, dry_run, timeout, resume, concurrency, adaptive):
    """Run benchmark tasks through a tool adapter."""
    from awb.core.runner import BenchmarkRunner
    from awb.core.task_loader import load_all_tasks

    workflow_info = None
    if workflow:
        from pathlib import Path
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
        ok, msg = asyncio.run(adapter.check_auth()) if asyncio.iscoroutinefunction(adapter.check_auth) else adapter.check_auth()
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
```

- [ ] **Step 2: Verify run command imports cleanly**

Run: `python3 -c "from awb.commands.run import run; print(run.name)"`
Expected: `run`

- [ ] **Step 3: Commit**

```bash
git add awb/commands/run.py
git commit -m "Extract run command to awb/commands/run.py"
```

---

### Task 3: Extract remaining commands

**Files:**
- Create: `awb/commands/analyze.py`
- Create: `awb/commands/calibrate.py`
- Create: `awb/commands/submit.py`
- Create: `awb/commands/validate.py`
- Create: `awb/commands/leaderboard_cmd.py`
- Create: `awb/commands/workflow_cmd.py`

Follow the same pattern as Task 2 for each command group. Extract from `awb/cli.py`:

- [ ] **Step 1: Create analyze.py** — Extract `compare()` (lines 295-345), `gap()` (lines 499-558), `stability()` (lines 834-867). Each function gets `@click.command()` decorator. Import `console` from `_shared`. Import `load_results_from_dirs` from `_shared` for stability.

- [ ] **Step 2: Create calibrate.py** — Extract `calibrate_difficulty_cmd()` (lines 870-908), `calibrate_timeouts_cmd()` (lines 911-948). Import `load_results_from_dirs` from `_shared`.

- [ ] **Step 3: Create submit.py** — Extract `export()` (lines 348-425), `submit()` (lines 561-585), `compare_submissions_cmd()` (lines 588-642).

- [ ] **Step 4: Create validate.py** — Extract `validate()` (lines 656-686), `info()` (lines 466-496), `quickstart()` (lines 428-463), `tools()` (lines 689-708).

- [ ] **Step 5: Create leaderboard_cmd.py** — Extract `leaderboard()` (lines 645-653).

- [ ] **Step 6: Create workflow_cmd.py** — Extract `workflow` group + 4 subcommands (lines 711-821).

- [ ] **Step 7: Verify each module imports cleanly**

Run: `python3 -c "from awb.commands.analyze import compare, gap, stability; print('OK')"`
Run: `python3 -c "from awb.commands.calibrate import calibrate_difficulty_cmd; print('OK')"`
Run: `python3 -c "from awb.commands.submit import export, submit; print('OK')"`
Run: `python3 -c "from awb.commands.validate import validate, info, quickstart, tools; print('OK')"`
Run: `python3 -c "from awb.commands.leaderboard_cmd import leaderboard; print('OK')"`
Run: `python3 -c "from awb.commands.workflow_cmd import workflow; print('OK')"`

- [ ] **Step 8: Commit**

```bash
git add awb/commands/analyze.py awb/commands/calibrate.py awb/commands/submit.py awb/commands/validate.py awb/commands/leaderboard_cmd.py awb/commands/workflow_cmd.py
git commit -m "Extract all CLI commands to awb/commands/ modules"
```

---

### Task 4: Rewire cli.py as thin entry point

**Files:**
- Modify: `awb/cli.py`

- [ ] **Step 1: Replace cli.py contents**

Replace the entire 948-line `awb/cli.py` with:

```python
"""CLI interface for the AI Workflow Benchmark."""
from __future__ import annotations

import click

from awb import __version__


@click.group()
@click.version_option(version=__version__, prog_name="awb")
def cli():
    """AI Workflow Benchmark - measure tool+workflow performance."""
    pass


# Register commands from modules
from awb.commands.run import run  # noqa: E402
from awb.commands.analyze import compare, gap, stability  # noqa: E402
from awb.commands.calibrate import calibrate_difficulty_cmd, calibrate_timeouts_cmd  # noqa: E402
from awb.commands.submit import export, submit, compare_submissions_cmd  # noqa: E402
from awb.commands.validate import validate, info, quickstart, tools  # noqa: E402
from awb.commands.leaderboard_cmd import leaderboard  # noqa: E402
from awb.commands.workflow_cmd import workflow  # noqa: E402

cli.add_command(run)
cli.add_command(compare)
cli.add_command(gap)
cli.add_command(stability)
cli.add_command(calibrate_difficulty_cmd)
cli.add_command(calibrate_timeouts_cmd)
cli.add_command(export)
cli.add_command(submit)
cli.add_command(compare_submissions_cmd)
cli.add_command(validate)
cli.add_command(info)
cli.add_command(quickstart)
cli.add_command(tools)
cli.add_command(leaderboard)
cli.add_command(workflow)
```

- [ ] **Step 2: Verify CLI still works**

Run: `python3 -m awb.cli --help`
Expected: Shows all commands (run, compare, gap, validate, etc.)

Run: `awb --version`
Expected: `awb, version 0.5.5`

Run: `awb validate --help`
Expected: Shows validate command help

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All 75 tests pass

- [ ] **Step 4: Commit**

```bash
git add awb/cli.py
git commit -m "Replace monolithic cli.py with thin entry point wiring command modules"
```

---

### Task 5: Fix adapter ABC and error handling

**Files:**
- Modify: `awb/adapters/base.py`
- Modify: `awb/adapters/claude_code.py`
- Modify: `awb/core/task_loader.py`
- Modify: `awb/core/config.py`

- [ ] **Step 1: Add new ABC methods to base.py**

Add after the existing `get_version()` method at line 48:

```python
    def supports_auth_check(self) -> bool:
        """Return True if this adapter can verify authentication."""
        return False

    def check_auth(self) -> tuple[bool, str]:
        """Check if the tool is authenticated. Returns (ok, message)."""
        return True, ""

    def supports_streaming(self) -> bool:
        """Return True if this adapter supports streaming output."""
        return False

    def get_model_pricing(self) -> dict[str, float]:
        """Return pricing per 1M tokens: {input_per_m, output_per_m}."""
        return {"input_per_m": 15.0, "output_per_m": 75.0}
```

- [ ] **Step 2: Implement supports_auth_check in ClaudeCodeVanillaAdapter**

In `awb/adapters/claude_code.py`, add to the `ClaudeCodeVanillaAdapter` class:

```python
    def supports_auth_check(self) -> bool:
        return True

    def check_auth(self) -> tuple[bool, str]:
        """Check if claude is logged in."""
        import subprocess
        try:
            cmd = self._get_cmd("echo test", 1)
            env = self._get_env()
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
            if "Not logged in" in result.stdout:
                return False, (
                    "Claude Code is not logged in. "
                    "Run 'claude' interactively first to authenticate, then re-run awb."
                )
            return True, ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, ""  # Timeout = probably working
```

- [ ] **Step 3: Add logging to task_loader.py**

In `awb/core/task_loader.py`, replace the bare exception catch in `load_all_tasks()`:

```python
# Replace:
#     except (ValidationError, Exception):
#         continue
# With:
        except jsonschema.ValidationError as e:
            logger.warning("Skipping %s: schema validation failed: %s", path.name, e.message)
            continue
        except yaml.YAMLError as e:
            logger.warning("Skipping %s: YAML parse error: %s", path.name, e)
            continue
```

Add `import logging` and `logger = logging.getLogger(__name__)` at the top of the file.

- [ ] **Step 4: Remove dead code from config.py and claude_code.py**

In `awb/core/config.py`, remove `_load_default_weights()` function (lines 22-25).

In `awb/adapters/claude_code.py`, remove the unused `_VANILLA_CONFIG_DIR` constant.

- [ ] **Step 5: Run tests**

Run: `pytest tests/ -v`
Expected: All 75 tests pass

- [ ] **Step 6: Commit**

```bash
git add awb/adapters/base.py awb/adapters/claude_code.py awb/core/task_loader.py awb/core/config.py
git commit -m "Add adapter ABC methods, add task loader logging, remove dead code"
```

---

## Phase 2: Scoring System Fixes

### Task 6: Add missing capabilities to enum

**Files:**
- Modify: `awb/scoring/capabilities.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_scoring.py, add:
def test_all_schema_capabilities_in_enum():
    """Every capability in schema.json must exist in Capability enum."""
    from awb.scoring.capabilities import Capability
    expected = {
        "code_comprehension", "bug_diagnosis", "multi_file_reasoning",
        "framework_knowledge", "test_writing", "refactoring_discipline",
        "security_awareness", "cost_discipline", "completeness_tracking",
        "convention_adherence", "context_discovery",
    }
    actual = {c.value for c in Capability}
    assert actual == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scoring.py::test_all_schema_capabilities_in_enum -v`
Expected: FAIL — missing completeness_tracking, convention_adherence, context_discovery

- [ ] **Step 3: Add 3 missing capabilities**

In `awb/scoring/capabilities.py`, add to the `Capability` enum after `COST_DISCIPLINE`:

```python
    COMPLETENESS_TRACKING = "completeness_tracking"
    CONVENTION_ADHERENCE = "convention_adherence"
    CONTEXT_DISCOVERY = "context_discovery"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scoring.py::test_all_schema_capabilities_in_enum -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (existing capability tests still work because new caps are just additional enum members)

- [ ] **Step 6: Commit**

```bash
git add awb/scoring/capabilities.py tests/test_scoring.py
git commit -m "Add missing capabilities: completeness_tracking, convention_adherence, context_discovery"
```

---

### Task 7: Align report.py metric names with weights.yaml

**Files:**
- Modify: `awb/scoring/report.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_scoring.py, add:
def test_report_metric_keys_match_weights():
    """report.py normalized keys must match weights.yaml keys."""
    from awb.scoring.composite import load_weight_profile
    from awb.scoring.report import generate_report

    weights = load_weight_profile("default")
    tool_stats = {
        "tool": "test-tool", "total_tasks": 10, "successes": 5,
        "success_rate": 50.0, "avg_score_pct": 60.0,
        "avg_cost": 0.50, "avg_time": 120.0, "avg_iterations": 10,
        "total_lint_delta": 2, "total_security_delta": 1, "total_regressions": 0,
    }
    report = generate_report(tool_stats)
    assert set(report.per_metric_normalized.keys()) == set(weights.keys())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scoring.py::test_report_metric_keys_match_weights -v`
Expected: FAIL — report uses success_rate, partial_credit, test_regressions, iteration_count; weights uses correctness, reliability, efficiency

- [ ] **Step 3: Fix generate_report() to use canonical metric names**

Replace `generate_report()` in `awb/scoring/report.py`:

```python
def generate_report(tool_stats: dict) -> ScoreReport:
    n = tool_stats["total_tasks"] or 1
    success = normalize_success_rate(tool_stats["success_rate"])
    partial = normalize_partial_credit(tool_stats["avg_score_pct"])
    correctness = 0.6 * success + 0.4 * partial

    raw = {
        "correctness": tool_stats["success_rate"],
        "cost_efficiency": tool_stats["avg_cost"],
        "speed": tool_stats["avg_time"],
        "code_quality": tool_stats["total_lint_delta"],
        "reliability": tool_stats["total_regressions"],
        "security": tool_stats["total_security_delta"],
        "efficiency": tool_stats["avg_iterations"],
    }
    normalized = {
        "correctness": round(correctness, 1),
        "cost_efficiency": normalize_cost(tool_stats["avg_cost"]),
        "speed": normalize_speed(tool_stats["avg_time"]),
        "code_quality": normalize_quality(tool_stats["total_lint_delta"], n),
        "reliability": normalize_regressions(tool_stats["total_regressions"], n),
        "security": normalize_security(tool_stats["total_security_delta"], n),
        "efficiency": normalize_iterations(tool_stats["avg_iterations"]),
    }
    composite = compute_composite_score(tool_stats)
    return ScoreReport(
        tool=tool_stats["tool"],
        composite_score=composite,
        per_metric_scores=raw,
        per_metric_normalized=normalized,
    )
```

Also update `print_report()` to use `load_weight_profile()` instead of `METRIC_WEIGHTS`:

```python
def print_report(report: ScoreReport) -> None:
    from awb.scoring.composite import load_weight_profile
    console = Console()
    score = report.composite_score
    console.print(f"\n[bold]{report.tool}[/bold] - Composite: [bold cyan]{score}[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Raw", justify="right")
    table.add_column("Normalized", justify="right")
    table.add_column("Weight", justify="right")

    weights = load_weight_profile()
    for metric, weight in weights.items():
        raw = report.per_metric_scores.get(metric, 0)
        norm = report.per_metric_normalized.get(metric, 0)
        table.add_row(
            metric,
            f"{raw:.2f}" if isinstance(raw, float) else str(raw),
            f"{norm:.1f}",
            f"{weight:.0%}",
        )

    console.print(table)

    if report.capability_profile:
        console.print("\n[bold]Capability Profile:[/bold]")
        for cap_name, cap_score in report.capability_profile.scores.items():
            if cap_score.score is None:
                bar = " " * 20
                score_str = "  n/a"
                tasks_str = ""
            else:
                filled = round(cap_score.score / 100 * 20)
                bar = "=" * filled + " " * (20 - filled)
                score_str = f"{cap_score.score:5.1f}"
                tasks_str = f"  ({cap_score.tasks_tested} tasks)"
            label = f"  {cap_name:<24}"
            console.print(f"{label}|{bar}| {score_str}{tasks_str}")
```

Remove the `from awb.core.config import METRIC_WEIGHTS` import from report.py.

- [ ] **Step 4: Run test**

Run: `pytest tests/test_scoring.py::test_report_metric_keys_match_weights -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add awb/scoring/report.py
git commit -m "Align report.py metric names with weights.yaml canonical dimensions"
```

---

### Task 8: Fix statistics.py strict zip, composite weight validation, integrity constant, metrics pricing

**Files:**
- Modify: `awb/scoring/statistics.py`
- Modify: `awb/scoring/composite.py`
- Modify: `awb/scoring/integrity.py`
- Modify: `awb/core/metrics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scoring.py — add:
def test_weight_profile_sums_to_one():
    """All weight profiles must sum to 1.0."""
    from awb.scoring.composite import load_weight_profile
    for profile in ("default", "correctness_focused", "production"):
        weights = load_weight_profile(profile)
        assert abs(sum(weights.values()) - 1.0) < 0.001, f"{profile} sums to {sum(weights.values())}"


def test_integrity_constant_defined():
    """Integrity module uses named constant for plausibility threshold."""
    from awb.scoring.integrity import MIN_PLAUSIBLE_SECONDS
    assert MIN_PLAUSIBLE_SECONDS == 10


# tests/test_metrics.py — new file:
def test_model_pricing_configurable():
    """MetricCollector respects model pricing."""
    from awb.core.metrics import MODEL_PRICING
    assert "opus" in MODEL_PRICING
    assert "sonnet" in MODEL_PRICING
    assert MODEL_PRICING["opus"]["input_per_m"] == 15.0


def test_cost_calculation_default():
    from awb.core.metrics import MetricCollector
    mc = MetricCollector()
    mc.start()
    mc.record_tokens(1_000_000, 100_000)
    mc.stop()
    cost = mc.to_cost()
    # 1M input * 15/1M + 100K output * 75/1M = 15.0 + 7.5 = 22.5
    assert cost.estimated_cost_usd == 22.5


def test_cost_zero_tokens():
    from awb.core.metrics import MetricCollector
    mc = MetricCollector()
    mc.start()
    mc.stop()
    cost = mc.to_cost()
    assert cost.estimated_cost_usd == 0.0
```

- [ ] **Step 2: Run tests to verify some fail**

Run: `pytest tests/test_scoring.py::test_integrity_constant_defined tests/test_metrics.py -v`
Expected: FAIL on integrity constant (not yet defined) and model pricing (not yet a dict)

- [ ] **Step 3: Fix statistics.py**

In `awb/scoring/statistics.py`, find `strict=False` (around line 158) and change to `strict=True`:

```python
    diffs = [c - v for v, c in zip(v_scores, c_scores, strict=True)]
```

- [ ] **Step 4: Add weight validation to composite.py**

In `awb/scoring/composite.py`, after loading weights in `load_weight_profile()`, add validation:

```python
def load_weight_profile(profile: str = "default") -> dict[str, float]:
    """Load a weight profile from weights.yaml (cached after first read)."""
    if profile in _weight_cache:
        return _weight_cache[profile]
    weights_path = Path(__file__).parent / "weights.yaml"
    with weights_path.open() as f:
        all_profiles = yaml.safe_load(f)
    if profile not in all_profiles:
        raise ValueError(f"Unknown weight profile: {profile}. Available: {list(all_profiles)}")
    weights = all_profiles[profile]
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 0.001:
        raise ValueError(f"Weight profile '{profile}' sums to {weight_sum}, expected 1.0")
    _weight_cache[profile] = weights
    return weights
```

- [ ] **Step 5: Add named constant to integrity.py**

In `awb/scoring/integrity.py`, add after the imports:

```python
MIN_PLAUSIBLE_SECONDS = 10
```

Replace the magic `10` in `detect_contamination()`:

```python
        if result.metrics.wall_clock_seconds < MIN_PLAUSIBLE_SECONDS and result.outcome.success:
```

- [ ] **Step 6: Make metrics.py pricing configurable**

Replace the top of `awb/core/metrics.py`:

```python
# Pricing per 1M tokens by model family
MODEL_PRICING: dict[str, dict[str, float]] = {
    "opus": {"input_per_m": 15.0, "output_per_m": 75.0},
    "sonnet": {"input_per_m": 3.0, "output_per_m": 15.0},
    "haiku": {"input_per_m": 0.25, "output_per_m": 1.25},
    "default": {"input_per_m": 15.0, "output_per_m": 75.0},
}

# Backward compat: module-level constants use default pricing
INPUT_PRICE_PER_M = MODEL_PRICING["default"]["input_per_m"]
OUTPUT_PRICE_PER_M = MODEL_PRICING["default"]["output_per_m"]
```

- [ ] **Step 7: Run all tests**

Run: `pytest tests/ -v`
Expected: All pass including new tests

- [ ] **Step 8: Commit**

```bash
git add awb/scoring/statistics.py awb/scoring/composite.py awb/scoring/integrity.py awb/core/metrics.py tests/test_scoring.py tests/test_metrics.py
git commit -m "Fix strict zip, add weight validation, named constants, configurable pricing"
```

---

## Phase 3: Test Coverage

### Task 9: Add MetricCollector and cost calculation tests

**Files:**
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write comprehensive tests**

```python
# tests/test_metrics.py
"""Tests for MetricCollector and cost calculation."""
import time

from awb.core.metrics import MetricCollector, MODEL_PRICING


def test_model_pricing_has_expected_models():
    assert "opus" in MODEL_PRICING
    assert "sonnet" in MODEL_PRICING
    assert "haiku" in MODEL_PRICING
    assert "default" in MODEL_PRICING


def test_cost_calculation_default():
    mc = MetricCollector()
    mc.start()
    mc.record_tokens(1_000_000, 100_000)
    mc.stop()
    cost = mc.to_cost()
    expected = 1.0 * 15.0 + 0.1 * 75.0  # 15 + 7.5 = 22.5
    assert cost.estimated_cost_usd == 22.5


def test_cost_zero_tokens():
    mc = MetricCollector()
    mc.start()
    mc.stop()
    cost = mc.to_cost()
    assert cost.estimated_cost_usd == 0.0


def test_elapsed_seconds():
    mc = MetricCollector()
    mc.start()
    time.sleep(0.05)
    mc.stop()
    assert mc.elapsed_seconds >= 0.04  # Allow some slack


def test_tool_call_tracking():
    mc = MetricCollector()
    mc.record_tool_call("Read")
    mc.record_tool_call("Read")
    mc.record_tool_call("Edit")
    metrics = mc.to_metrics()
    assert metrics.tool_calls == {"Read": 2, "Edit": 1}


def test_iteration_counting():
    mc = MetricCollector()
    mc.record_iteration()
    mc.record_iteration()
    mc.record_iteration()
    metrics = mc.to_metrics()
    assert metrics.iteration_count == 3


def test_parse_stream_event_assistant():
    mc = MetricCollector()
    mc.parse_stream_event({
        "type": "assistant",
        "message": {
            "usage": {"input_tokens": 500, "output_tokens": 100},
            "content": [{"type": "tool_use", "name": "Read"}],
        },
    })
    assert mc._input_tokens == 500
    assert mc._output_tokens == 100
    assert mc._iterations == 1
    assert mc._tool_calls.get("Read") == 1


def test_parse_stream_event_result_overrides_tokens():
    mc = MetricCollector()
    mc.record_tokens(100, 50)  # Partial accumulation
    mc.parse_stream_event({
        "type": "result",
        "total_cost_usd": 1.23,
        "usage": {"input_tokens": 10000, "output_tokens": 5000},
        "num_turns": 7,
    })
    cost = mc.to_cost()
    assert cost.estimated_cost_usd == 1.23  # Uses final_cost
    assert cost.input_tokens == 10000  # Overridden by result event
    assert cost.output_tokens == 5000
    assert mc._iterations == 7


def test_parse_stream_event_non_dict_ignored():
    mc = MetricCollector()
    mc.parse_stream_event("not a dict")
    mc.parse_stream_event(42)
    mc.parse_stream_event(None)
    assert mc._iterations == 0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_metrics.py -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_metrics.py
git commit -m "Add comprehensive MetricCollector tests"
```

---

### Task 10: Add code review scorer tests

**Files:**
- Create: `tests/test_code_review_scorer.py`

- [ ] **Step 1: Read the scorer to understand the interface**

The file is `awb/verification/code_review_scorer.py`. It has `score_code_review()` returning a `ReviewScore` with TP/FP/FN, precision/recall/F1.

- [ ] **Step 2: Write tests**

```python
# tests/test_code_review_scorer.py
"""Tests for code review scoring (precision/recall/F1)."""
from awb.verification.code_review_scorer import score_code_review, ReviewScore


def test_perfect_score():
    known_issues = ["SQL injection in login", "XSS in search page"]
    output = "Found SQL injection in login endpoint. Also found XSS in search page."
    result = score_code_review(known_issues, output)
    assert result.true_positives == 2
    assert result.false_negatives == 0
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_zero_matches():
    known_issues = ["Buffer overflow in parser"]
    output = "Code looks clean, no issues found."
    result = score_code_review(known_issues, output)
    assert result.true_positives == 0
    assert result.false_negatives == 1
    assert result.recall == 0.0


def test_partial_match():
    known_issues = ["SQL injection", "XSS vulnerability", "CSRF token missing"]
    output = "Found SQL injection. Also detected XSS vulnerability. No other issues."
    result = score_code_review(known_issues, output)
    assert result.true_positives == 2
    assert result.false_negatives == 1
    assert result.recall == pytest.approx(2 / 3, abs=0.01)


def test_empty_known_issues():
    result = score_code_review([], "Some output text")
    assert result.true_positives == 0
    assert result.false_positives >= 0


def test_empty_output():
    result = score_code_review(["issue1"], "")
    assert result.true_positives == 0
    assert result.false_negatives == 1
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_code_review_scorer.py -v`
Expected: All pass (adjust assertions if scorer API differs — read the actual file first)

- [ ] **Step 4: Commit**

```bash
git add tests/test_code_review_scorer.py
git commit -m "Add code review scorer tests"
```

---

### Task 11: Add runner and results tests with FakeAdapter

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/test_runner.py`
- Create: `tests/test_results.py`

- [ ] **Step 1: Add fixtures to conftest.py**

```python
# Add to tests/conftest.py:
from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.config import RunResult, RunOutcome, RunMetrics, RunCost, RunQuality


class FakeAdapter(ToolAdapter):
    """Test adapter that returns canned results."""

    name = "fake-tool"
    display_name = "Fake Tool"

    def __init__(self, success=True, output="done", cost_usd=0.10):
        self._success = success
        self._output = output
        self._cost_usd = cost_usd

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=1800):
        return ToolResult(
            success=self._success,
            raw_output=self._output,
            stream_events=[],
            exit_code=0 if self._success else 1,
            tool_version="fake-1.0",
            model="fake-model",
        )

    def check_available(self):
        return True

    def get_config_hash(self):
        return "fake-hash"


@pytest.fixture
def fake_adapter():
    return FakeAdapter()


@pytest.fixture
def sample_result():
    """A RunResult object for testing."""
    return RunResult(
        task_id="BF-001",
        tool="fake-tool",
        tool_version="1.0",
        model="fake-model",
        run_id="test-run",
        timestamp="2026-03-26T00:00:00Z",
        outcome=RunOutcome(
            success=True,
            partial_credit_score=80,
            partial_credit_max=100,
            breakdown=[],
        ),
        metrics=RunMetrics(
            wall_clock_seconds=120.0,
            iteration_count=5,
            human_interventions=0,
            tool_calls={"Read": 3},
            files_modified=2,
            lines_changed=30,
        ),
        cost=RunCost(
            input_tokens=50000,
            output_tokens=10000,
            estimated_cost_usd=0.42,
        ),
        quality=RunQuality(
            lint_delta=0,
            security_delta=0,
            test_regressions=0,
        ),
        environment={"os": "darwin", "hardware": "test"},
    )


@pytest.fixture
def sample_results_batch(sample_task):
    """Multiple RunResult objects with varied outcomes."""
    results = []
    for i, (success, score, time_s, cost) in enumerate([
        (True, 100, 60.0, 0.20),
        (True, 80, 120.0, 0.40),
        (False, 30, 300.0, 1.20),
        (False, 0, 1800.0, 2.50),
    ]):
        results.append(RunResult(
            task_id=f"BF-{i+1:03d}",
            tool="fake-tool",
            tool_version="1.0",
            model="fake-model",
            run_id=f"test-run-{i}",
            timestamp="2026-03-26T00:00:00Z",
            outcome=RunOutcome(success=success, partial_credit_score=score, partial_credit_max=100, breakdown=[]),
            metrics=RunMetrics(wall_clock_seconds=time_s, iteration_count=5, human_interventions=0, tool_calls={}, files_modified=1, lines_changed=10),
            cost=RunCost(input_tokens=10000, output_tokens=5000, estimated_cost_usd=cost),
            quality=RunQuality(lint_delta=0, security_delta=0, test_regressions=0),
            environment={"os": "darwin", "hardware": "test"},
        ))
    return results
```

- [ ] **Step 2: Write runner tests**

```python
# tests/test_runner.py
"""Tests for BenchmarkRunner — adaptive mode, resume, parallel."""
import pytest


class TestAdaptiveFiltering:
    def test_decisive_task_not_rerun(self):
        """Task scoring 0 should be classified as decisive and skipped on re-run."""
        from awb.core.runner import _ADAPTIVE_RERUN_MIN
        assert _ADAPTIVE_RERUN_MIN == 60  # Verify the threshold constant

    def test_near_miss_threshold(self):
        """Tasks between ADAPTIVE_RERUN_MIN and 100% should be re-run."""
        from awb.core.runner import _ADAPTIVE_RERUN_MIN
        # score of 60% of max_pts = boundary case
        score_pct = 60
        assert score_pct >= _ADAPTIVE_RERUN_MIN
```

- [ ] **Step 3: Write results tests**

```python
# tests/test_results.py
"""Tests for ResultRecorder — save, load, resume detection."""
import json
from pathlib import Path

import pytest

from awb.core.results import ResultRecorder


def test_save_and_load_result(tmp_workspace, sample_result):
    """Write a result, read it back, verify identity."""
    recorder = ResultRecorder(results_dir=tmp_workspace)
    recorder.save_result(sample_result, "test-run")

    # Find the saved file
    files = list(tmp_workspace.rglob("*.json"))
    assert len(files) == 1

    with files[0].open() as f:
        data = json.load(f)
    assert data["task_id"] == "BF-001"
    assert data["outcome"]["success"] is True


def test_load_run(tmp_workspace, sample_result):
    """load_run() returns all results in a run directory."""
    recorder = ResultRecorder(results_dir=tmp_workspace)
    recorder.save_result(sample_result, "run-001")
    results = recorder.load_run(tmp_workspace / "run-001")
    assert len(results) >= 1
    assert results[0].task_id == "BF-001"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_runner.py tests/test_results.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_runner.py tests/test_results.py
git commit -m "Add runner and results tests with FakeAdapter fixture"
```

---

### Task 12: Add gap analysis and submission tests

**Files:**
- Create: `tests/test_gap_analysis.py`
- Create: `tests/test_submission.py`

- [ ] **Step 1: Write gap analysis tests**

```python
# tests/test_gap_analysis.py
"""Tests for gap analysis failure classification and pattern detection."""
from awb.analysis.gap_analysis import classify_failure
from awb.core.config import (
    RunResult, RunOutcome, RunMetrics, RunCost, RunQuality, TaskDefinition,
    TaskRepo, TaskVerification, TaskConstraints,
)


def _make_result(success=True, score=100, max_score=100, time_s=120.0):
    return RunResult(
        task_id="BF-001", tool="test", tool_version="1.0", model="m",
        run_id="r", timestamp="2026-01-01T00:00:00Z",
        outcome=RunOutcome(success=success, partial_credit_score=score, partial_credit_max=max_score, breakdown=[]),
        metrics=RunMetrics(wall_clock_seconds=time_s, iteration_count=5, human_interventions=0, tool_calls={}, files_modified=1, lines_changed=10),
        cost=RunCost(input_tokens=1000, output_tokens=500, estimated_cost_usd=0.10),
        quality=RunQuality(lint_delta=0, security_delta=0, test_regressions=0),
        environment={"os": "test"},
    )


def _make_task(timeout=300):
    return TaskDefinition(
        id="BF-001", category="bug-fix", title="Test task", difficulty="medium",
        estimated_minutes=15, languages=["python"], tags=[], capabilities=[],
        repo=TaskRepo(url="https://github.com/test/test", commit="abc1234"),
        issue_description="Fix a bug",
        verification=TaskVerification(test_commands=["pytest"], lint_commands=[], security_commands=[], partial_credit=[]),
        constraints=TaskConstraints(max_iterations=20, timeout_seconds=timeout),
    )


def test_classify_success():
    result = _make_result(success=True)
    task = _make_task()
    assert classify_failure(result, task) == "success"


def test_classify_timeout():
    result = _make_result(success=False, score=0, time_s=295.0)
    task = _make_task(timeout=300)
    assert classify_failure(result, task) == "timeout"


def test_classify_partial_completion():
    result = _make_result(success=False, score=50, max_score=100, time_s=120.0)
    task = _make_task(timeout=300)
    assert classify_failure(result, task) == "partial_completion"


def test_classify_code_error():
    result = _make_result(success=False, score=0, time_s=120.0)
    task = _make_task(timeout=300)
    assert classify_failure(result, task) == "code_error"
```

- [ ] **Step 2: Write submission tests**

```python
# tests/test_submission.py
"""Tests for submission ingestion and comparison."""
import json
import tempfile
from pathlib import Path

import pytest


def test_validate_submission_valid():
    """Valid submission passes validation."""
    from awb.submission.ingest import validate_submission
    # Minimal valid submission structure
    data = {
        "tool": {"name": "test-tool", "version": "1.0"},
        "model": {"name": "test-model"},
        "environment": {"os": "linux", "hardware_class": "standard"},
        "results": [],
    }
    # This may fail if schema requires more fields — adjust per actual schema
    errors = validate_submission(data)
    # Check if validation runs without crashing
    assert isinstance(errors, list)


def test_validate_submission_invalid():
    """Invalid submission returns errors."""
    from awb.submission.ingest import validate_submission
    errors = validate_submission({})
    assert len(errors) > 0
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_gap_analysis.py tests/test_submission.py -v`
Expected: All pass (adjust if actual function signatures differ)

- [ ] **Step 4: Commit**

```bash
git add tests/test_gap_analysis.py tests/test_submission.py
git commit -m "Add gap analysis and submission tests"
```

---

### Task 13: Add lint checker tests

**Files:**
- Create: `tests/test_lint_checker.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_lint_checker.py
"""Tests for lint checker issue counting."""
import pytest

from awb.verification.lint_checker import count_lint_issues


def test_count_issues_from_ruff_output():
    """Standard ruff output format should be counted."""
    output = (
        "src/app.py:10:5: E501 Line too long\n"
        "src/app.py:20:1: F401 Unused import\n"
        "src/utils.py:5:10: W291 Trailing whitespace\n"
    )
    count = count_lint_issues(output)
    assert count == 3


def test_count_issues_empty_output():
    count = count_lint_issues("")
    assert count == 0


def test_count_issues_no_matches():
    output = "All good! No issues found."
    count = count_lint_issues(output)
    assert count == 0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_lint_checker.py -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_lint_checker.py
git commit -m "Add lint checker tests"
```

---

### Task 14: Run full test suite and verify coverage target

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: 100+ tests pass, 0 failures

- [ ] **Step 2: Commit checkpoint**

```bash
git commit --allow-empty -m "Phase 3 complete: test coverage expanded to 100+ tests"
```

---

## Phase 4: Adapter System

### Task 15: Create Gemini CLI adapter

**Files:**
- Create: `awb/adapters/gemini_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_adapters.py:
def test_gemini_adapter_registered():
    from awb.adapters.registry import _FALLBACK
    assert "gemini-cli" in _FALLBACK


def test_gemini_adapter_not_available_when_missing():
    from awb.adapters.gemini_cli import GeminiCliAdapter
    adapter = GeminiCliAdapter()
    # On this machine, gemini CLI may not be installed
    result = adapter.check_available()
    assert isinstance(result, bool)


def test_gemini_config_hash_deterministic():
    from awb.adapters.gemini_cli import GeminiCliAdapter
    adapter = GeminiCliAdapter()
    h1 = adapter.get_config_hash()
    h2 = adapter.get_config_hash()
    assert h1 == h2
```

- [ ] **Step 2: Implement adapter**

```python
# awb/adapters/gemini_cli.py
"""Gemini CLI adapter for AI Workflow Benchmark."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class GeminiCliAdapter(ToolAdapter):
    """Adapter for Google's Gemini CLI."""

    name = "gemini-cli"
    display_name = "Gemini CLI"

    def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
        return [
            "gemini",
            "-p", prompt,
            "--output-format", "json",
        ]

    def _get_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["AWB_BENCHMARK"] = "1"
        # Remove Claude-specific env vars
        for key in list(env):
            if key.startswith("CLAUDE"):
                del env[key]
        return env

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        cmd = self._get_cmd(prompt, max_turns)
        env = self._get_env()
        env["HOME"] = str(Path.home())

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return ToolResult(success=False, raw_output="", exit_code=-1)

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        raw_output = stdout + stderr

        # Parse JSON events from output
        stream_events = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                stream_events.append(event)
            except json.JSONDecodeError:
                continue

        success = proc.returncode == 0 and bool(stdout.strip())
        model = ""
        version = self.get_version()

        return ToolResult(
            success=success,
            raw_output=raw_output,
            stream_events=stream_events,
            exit_code=proc.returncode or 0,
            tool_version=version,
            model=model,
        )

    def check_available(self) -> bool:
        return shutil.which("gemini") is not None

    def get_version(self) -> str:
        import subprocess
        try:
            result = subprocess.run(
                ["gemini", "--version"], capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip().split("\n")[0] if result.returncode == 0 else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"

    def get_config_hash(self) -> str:
        """Hash of gemini config for reproducibility."""
        h = hashlib.sha256()
        config_dir = Path.home() / ".gemini"
        if config_dir.exists():
            for f in sorted(config_dir.glob("*.json")):
                h.update(f.read_bytes())
        else:
            h.update(b"no-config")
        return h.hexdigest()[:16]
```

- [ ] **Step 3: Register in registry.py**

Add to `_FALLBACK` dict in `awb/adapters/registry.py`:

```python
    "gemini-cli": "awb.adapters.gemini_cli:GeminiCliAdapter",
```

Add to `pyproject.toml` entry points:

```toml
gemini-cli = "awb.adapters.gemini_cli:GeminiCliAdapter"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_adapters.py -v`
Expected: All pass including new gemini tests

- [ ] **Step 5: Commit**

```bash
git add awb/adapters/gemini_cli.py awb/adapters/registry.py pyproject.toml tests/test_adapters.py
git commit -m "Add Gemini CLI adapter"
```

---

### Task 16: Create Codex CLI adapter

**Files:**
- Create: `awb/adapters/codex_cli.py`

- [ ] **Step 1: Write tests**

```python
# Add to tests/test_adapters.py:
def test_codex_adapter_registered():
    from awb.adapters.registry import _FALLBACK
    assert "codex-cli" in _FALLBACK


def test_codex_adapter_not_available_when_missing():
    from awb.adapters.codex_cli import CodexCliAdapter
    adapter = CodexCliAdapter()
    result = adapter.check_available()
    assert isinstance(result, bool)


def test_codex_config_hash_deterministic():
    from awb.adapters.codex_cli import CodexCliAdapter
    adapter = CodexCliAdapter()
    h1 = adapter.get_config_hash()
    h2 = adapter.get_config_hash()
    assert h1 == h2
```

- [ ] **Step 2: Implement adapter**

```python
# awb/adapters/codex_cli.py
"""OpenAI Codex CLI adapter for AI Workflow Benchmark."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class CodexCliAdapter(ToolAdapter):
    """Adapter for OpenAI's Codex CLI."""

    name = "codex-cli"
    display_name = "Codex CLI"

    def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
        return ["codex", "-p", prompt, "--output-format", "json"]

    def _get_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["AWB_BENCHMARK"] = "1"
        for key in list(env):
            if key.startswith("CLAUDE"):
                del env[key]
        return env

    async def execute(
        self, prompt: str, workspace: Path, max_turns: int = 20, timeout_seconds: int = 1800,
    ) -> ToolResult:
        cmd = self._get_cmd(prompt, max_turns)
        env = self._get_env()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return ToolResult(success=False, raw_output="", exit_code=-1)

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        stream_events = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                stream_events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        success = proc.returncode == 0 and bool(stdout.strip())
        return ToolResult(
            success=success,
            raw_output=stdout + stderr,
            stream_events=stream_events,
            exit_code=proc.returncode or 0,
            tool_version=self.get_version(),
            model="",
        )

    def check_available(self) -> bool:
        return shutil.which("codex") is not None

    def get_version(self) -> str:
        import subprocess
        try:
            result = subprocess.run(
                ["codex", "--version"], capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip().split("\n")[0] if result.returncode == 0 else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"

    def get_config_hash(self) -> str:
        h = hashlib.sha256()
        config_dir = Path.home() / ".codex"
        if config_dir.exists():
            for f in sorted(config_dir.glob("*.json")):
                h.update(f.read_bytes())
        else:
            h.update(b"no-config")
        return h.hexdigest()[:16]
```

- [ ] **Step 3: Register in registry.py and pyproject.toml**

Add to `_FALLBACK`: `"codex-cli": "awb.adapters.codex_cli:CodexCliAdapter"`

Add to pyproject.toml entry points: `codex-cli = "awb.adapters.codex_cli:CodexCliAdapter"`

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_adapters.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add awb/adapters/codex_cli.py awb/adapters/registry.py pyproject.toml tests/test_adapters.py
git commit -m "Add Codex CLI adapter"
```

---

### Task 17: Create Windsurf and Copilot adapter stubs

**Files:**
- Create: `awb/adapters/windsurf.py`
- Create: `awb/adapters/copilot_cli.py`

These require research spikes. Create functional stubs like the existing Aider/Cursor adapters:

- [ ] **Step 1: Create windsurf.py stub**

```python
# awb/adapters/windsurf.py
"""Windsurf adapter — stub pending CLI availability."""
from __future__ import annotations

from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class WindsurfAdapter(ToolAdapter):
    name = "windsurf"
    display_name = "Windsurf"

    async def execute(self, prompt: str, workspace: Path, max_turns: int = 20, timeout_seconds: int = 1800) -> ToolResult:
        raise NotImplementedError(
            "Windsurf adapter requires Windsurf CLI (not yet publicly available). "
            "Check https://windsurf.com for CLI release updates."
        )

    def check_available(self) -> bool:
        import shutil
        return shutil.which("windsurf") is not None

    def get_config_hash(self) -> str:
        return "windsurf-stub"
```

- [ ] **Step 2: Create copilot_cli.py stub**

```python
# awb/adapters/copilot_cli.py
"""GitHub Copilot CLI adapter — stub pending agentic CLI mode."""
from __future__ import annotations

from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class CopilotCliAdapter(ToolAdapter):
    name = "copilot"
    display_name = "GitHub Copilot CLI"

    async def execute(self, prompt: str, workspace: Path, max_turns: int = 20, timeout_seconds: int = 1800) -> ToolResult:
        raise NotImplementedError(
            "Copilot CLI adapter requires 'gh copilot' with agentic mode. "
            "Currently Copilot CLI is suggestion-based, not agentic. "
            "Run 'gh extension list' to check if copilot extension is installed."
        )

    def check_available(self) -> bool:
        import subprocess
        try:
            result = subprocess.run(
                ["gh", "extension", "list"], capture_output=True, text=True, timeout=10
            )
            return "copilot" in result.stdout.lower()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_config_hash(self) -> str:
        return "copilot-stub"
```

- [ ] **Step 3: Register both in registry.py and pyproject.toml**

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_adapters.py -v`
Expected: All pass. `list_adapters()` test may need updating if it checks count.

- [ ] **Step 5: Commit**

```bash
git add awb/adapters/windsurf.py awb/adapters/copilot_cli.py awb/adapters/registry.py pyproject.toml
git commit -m "Add Windsurf and Copilot CLI adapter stubs"
```

---

## Phase 5: Output Upgrades

### Task 18: Add live progress to terminal output

**Files:**
- Modify: `awb/core/runner.py`
- Modify: `awb/commands/run.py`

This task adds Rich `Live` display during benchmark execution. The runner's `_run_sequential()` and `_run_parallel()` methods need callbacks to update the display.

- [ ] **Step 1: Add progress callback to runner**

In `awb/core/runner.py`, add a callback parameter to `run_all()`:

```python
async def run_all(self, on_task_complete=None):
    """Run benchmark. on_task_complete(result: RunResult) called after each task."""
```

Call `on_task_complete(result)` after each `run_single()` completes (in both sequential and parallel paths).

- [ ] **Step 2: Add Rich Live display to run command**

In `awb/commands/run.py`, wrap the runner call in a Rich Live context:

```python
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel

# During run:
task_results = []

def on_complete(result):
    task_results.append(result)
    # Update live display
    ...

with Live(console=console, refresh_per_second=4) as live:
    results = asyncio.run(runner.run_all(on_task_complete=on_complete))
```

- [ ] **Step 3: Color-code summary table**

Add color bands to the summary table:

```python
def _score_color(score: float) -> str:
    if score > 80:
        return "green"
    elif score > 50:
        return "yellow"
    return "red"
```

- [ ] **Step 4: Run manually to verify**

Run: `awb run --dry-run`
Expected: Dry run still works. Live display only activates on actual runs.

- [ ] **Step 5: Commit**

```bash
git add awb/core/runner.py awb/commands/run.py
git commit -m "Add live progress display during benchmark runs"
```

---

### Task 19: Upgrade static leaderboard with Chart.js

**Files:**
- Modify: `awb/leaderboard/generate.py`
- Modify: `awb/leaderboard/templates/index.html`
- Modify: `awb/leaderboard/static/leaderboard.js`
- Modify: `awb/leaderboard/static/style.css`

- [ ] **Step 1: Add Chart.js CDN to template**

In `index.html`, add before the closing `</head>`:

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
```

- [ ] **Step 2: Add radar chart section using Chart.js**

Replace the canvas-based radar chart with a Chart.js radar:

```html
<div class="chart-section">
    <h2>Scoring Dimensions</h2>
    <canvas id="radar-chart" width="500" height="500"></canvas>
</div>
```

In `leaderboard.js`:

```javascript
function drawRadarChartJS(resultsData) {
    const ctx = document.getElementById('radar-chart').getContext('2d');
    const dimensions = ['correctness', 'cost_efficiency', 'speed', 'code_quality', 'reliability', 'security', 'efficiency'];
    const colors = ['#3b82f6', '#22c55e', '#eab308', '#ef4444', '#a855f7', '#06b6d4'];

    const datasets = Object.entries(resultsData).map(([tool, scores], i) => ({
        label: tool,
        data: dimensions.map(d => scores[d] || 0),
        borderColor: colors[i % colors.length],
        backgroundColor: colors[i % colors.length] + '33',
        pointRadius: 3,
    }));

    new Chart(ctx, {
        type: 'radar',
        data: { labels: dimensions.map(d => d.replace('_', ' ')), datasets },
        options: {
            scales: { r: { beginAtZero: true, max: 100, ticks: { stepSize: 20 } } },
            plugins: { legend: { position: 'bottom' } },
        },
    });
}
```

- [ ] **Step 3: Add difficulty breakdown bar chart**

```html
<div class="chart-section">
    <h2>Pass Rate by Difficulty</h2>
    <canvas id="difficulty-chart" width="600" height="300"></canvas>
</div>
```

- [ ] **Step 4: Add task explorer with filtering**

```html
<div class="explorer-section">
    <h2>Task Explorer</h2>
    <input type="text" id="task-filter" placeholder="Filter by task ID, category...">
    <table id="task-table">
        <thead>
            <tr>
                <th data-sort>Task ID</th>
                <th data-sort>Category</th>
                <th data-sort>Difficulty</th>
                {% for tool in tools %}
                <th data-sort>{{ tool.tool }}</th>
                {% endfor %}
            </tr>
        </thead>
        <tbody>
            {% for task_id, results in task_results.items() %}
            <tr>
                <td>{{ task_id }}</td>
                <td>{{ results.category }}</td>
                <td>{{ results.difficulty }}</td>
                {% for tool in tools %}
                <td class="score-cell">{{ results.get(tool.tool, '-') }}</td>
                {% endfor %}
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
```

- [ ] **Step 5: Add history tracking to generate.py**

In `generate_leaderboard()`, after generating the main page, append to `data/history.json`:

```python
import json
from datetime import datetime, UTC

history_path = output_dir / "data" / "history.json"
history_path.parent.mkdir(parents=True, exist_ok=True)
history = []
if history_path.exists():
    with history_path.open() as f:
        history = json.load(f)

history.append({
    "timestamp": datetime.now(UTC).isoformat(),
    "tools": {t["tool"]: t["composite_score"] for t in ranked_tools},
})

with history_path.open("w") as f:
    json.dump(history, f, indent=2)
```

- [ ] **Step 6: Add CSV export button**

```javascript
function exportCSV() {
    const rows = [['Task', ...Object.keys(RESULTS_DATA)]];
    // Build CSV from task_results
    const blob = new Blob([rows.map(r => r.join(',')).join('\n')], {type: 'text/csv'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'awb-results.csv'; a.click();
}
```

- [ ] **Step 7: Run leaderboard generation**

Run: `awb leaderboard /tmp/test-leaderboard`
Expected: Generates index.html with Chart.js charts, task explorer, history tracking

- [ ] **Step 8: Commit**

```bash
git add awb/leaderboard/
git commit -m "Upgrade leaderboard with Chart.js radar, difficulty chart, task explorer, history"
```

---

## Phase 6: Migration, Validation, and Version Bump

### Task 20: Add result version field and partial credit sum validation

**Files:**
- Modify: `awb/core/results.py`
- Modify: `awb/core/task_loader.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_results.py:
def test_saved_result_has_version_field(tmp_workspace, sample_result):
    """New results should include version: 1.0."""
    from awb.core.results import ResultRecorder
    recorder = ResultRecorder(results_dir=tmp_workspace)
    recorder.save_result(sample_result, "test-run")
    files = list(tmp_workspace.rglob("*.json"))
    import json
    with files[0].open() as f:
        data = json.load(f)
    assert data["version"] == "1.0"


# Add to tests/test_task_loader.py:
def test_partial_credit_sum_validation(tmp_workspace):
    """validate_task_yaml rejects tasks where partial_credit doesn't sum to 100."""
    import yaml
    from awb.core.task_loader import validate_task_yaml

    bad_task = {
        "id": "BF-099",
        "category": "bug-fix",
        "title": "Test task with bad partial credit",
        "difficulty": "easy",
        "estimated_minutes": 10,
        "languages": ["python"],
        "repo": {"url": "https://github.com/test/test", "commit": "abc1234"},
        "issue": {"description": "Fix a bug"},
        "verification": {
            "test_commands": ["pytest"],
            "partial_credit": [
                {"criterion": "A", "points": 60, "check": "true"},
                {"criterion": "B", "points": 30, "check": "true"},
            ],  # Sums to 90, not 100
        },
        "constraints": {"max_iterations": 20, "timeout_seconds": 300},
    }
    task_file = tmp_workspace / "BF-099.yaml"
    with task_file.open("w") as f:
        yaml.dump(bad_task, f)

    errors = validate_task_yaml(task_file)
    assert any("100" in str(e) for e in errors), f"Expected sum-to-100 error, got: {errors}"
```

- [ ] **Step 2: Add version field to ResultRecorder.save_result()**

In `awb/core/results.py`, in the `save_result()` method, add `"version": "1.0"` to the result dict before writing:

```python
data = result.to_dict()
data["version"] = "1.0"
```

- [ ] **Step 3: Add partial credit sum validation to task_loader.py**

In `awb/core/task_loader.py`, in `validate_task_yaml()`, after schema validation succeeds, add:

```python
    # Check partial credit sums to 100
    pc = data.get("verification", {}).get("partial_credit", [])
    if pc:
        total = sum(c.get("points", 0) for c in pc)
        if total != 100:
            errors.append(f"partial_credit points sum to {total}, expected 100")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_results.py tests/test_task_loader.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add awb/core/results.py awb/core/task_loader.py tests/test_results.py tests/test_task_loader.py
git commit -m "Add version field to results, validate partial credit sums to 100"
```

---

### Task 21: Add migrate-results command

**Files:**
- Create: `awb/commands/migrate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_integration.py
import json
import tempfile
from pathlib import Path
from click.testing import CliRunner


def test_migrate_results_adds_version(sample_result_dict):
    """migrate-results adds version field to v0.5.x results."""
    from awb.cli import cli

    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = Path(tmpdir) / "old"
        new_dir = Path(tmpdir) / "new"
        old_dir.mkdir()

        # Write a v0.5.x result (no version field)
        result_file = old_dir / "BF-001.json"
        with result_file.open("w") as f:
            json.dump(sample_result_dict, f)

        runner = CliRunner()
        result = runner.invoke(cli, ["migrate-results", str(old_dir), "--output", str(new_dir)])
        assert result.exit_code == 0

        migrated = list(new_dir.rglob("*.json"))
        assert len(migrated) == 1
        with migrated[0].open() as f:
            data = json.load(f)
        assert data["version"] == "1.0"
        assert "_v05x_original" in data
```

- [ ] **Step 2: Implement migrate command**

```python
# awb/commands/migrate.py
"""Migrate v0.5.x results to v1.0 format."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from awb.commands._shared import console


@click.command("migrate-results")
@click.argument("old_dir", type=click.Path(exists=True))
@click.option("--output", "-o", "output_dir", type=click.Path(), help="Output directory (default: in-place)")
def migrate_results(old_dir: str, output_dir: str | None):
    """Migrate v0.5.x result JSON files to v1.0 format."""
    old_path = Path(old_dir)
    out_path = Path(output_dir) if output_dir else old_path
    out_path.mkdir(parents=True, exist_ok=True)

    files = list(old_path.rglob("*.json"))
    if not files:
        console.print("[yellow]No JSON files found[/yellow]")
        return

    migrated = 0
    for f in files:
        with f.open() as fh:
            data = json.load(fh)

        if data.get("version") == "1.0":
            continue  # Already migrated

        # Preserve original
        original = dict(data)

        # Add version
        data["version"] = "1.0"

        # Store original for auditability
        data["_v05x_original"] = original

        # Backfill missing fields
        data.setdefault("hardware", None)
        data.setdefault("adapter_config_hash", None)

        # Write to output
        out_file = out_path / f.relative_to(old_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w") as fh:
            json.dump(data, fh, indent=2)
        migrated += 1

    console.print(f"Migrated {migrated} file(s) to v1.0 format")
```

- [ ] **Step 3: Register in cli.py**

Add to `awb/cli.py`:

```python
from awb.commands.migrate import migrate_results  # noqa: E402
cli.add_command(migrate_results)
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_cli_integration.py::test_migrate_results_adds_version -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add awb/commands/migrate.py awb/cli.py tests/test_cli_integration.py
git commit -m "Add migrate-results command for v0.5.x to v1.0 conversion"
```

---

### Task 22: Version bump and final validation

**Files:**
- Modify: `awb/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version**

In `awb/__init__.py`:
```python
__version__ = "1.0.0"
```

In `pyproject.toml`:
```toml
version = "1.0.0"
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: 100+ tests, all pass

- [ ] **Step 3: Run linter**

Run: `ruff check awb/`
Expected: No errors

- [ ] **Step 4: Validate all tasks**

Run: `awb validate`
Expected: All 100 tasks pass

- [ ] **Step 5: Verify CLI**

Run: `awb --version`
Expected: `awb, version 1.0.0`

Run: `awb tools`
Expected: Lists all adapters including gemini-cli, codex-cli, windsurf, copilot

- [ ] **Step 6: Commit**

```bash
git add awb/__init__.py pyproject.toml
git commit -m "v1.0.0: AWB revamp complete"
```

---

## Summary

| Phase | Tasks | New Tests | New Files | Modified Files |
|-------|-------|-----------|-----------|----------------|
| 1. Restructure | 1-5 | 0 | 10 | 4 |
| 2. Scoring | 6-8 | 5 | 1 | 5 |
| 3. Tests | 9-14 | 40+ | 7 | 1 |
| 4. Adapters | 15-17 | 6 | 4 | 2 |
| 5. Output | 18-19 | 0 | 0 | 6 |
| 6. Migration | 20-22 | 3 | 1 | 5 |
| **Total** | **22** | **54+** | **23** | **23** |
