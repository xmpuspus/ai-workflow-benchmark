"""Main benchmark orchestrator."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from awb.core.config import (
    RunEnvironment,
    RunOutcome,
    RunQuality,
    RunResult,
    TaskDefinition,
    WorkflowInfo,
)
from awb.core.metrics import MetricCollector
from awb.core.repo_manager import RepoManager
from awb.core.results import ResultRecorder
from awb.core.timeout import TaskTimeoutError, run_with_timeout
from awb.verification.lint_checker import count_lint_issues
from awb.verification.partial_credit import evaluate_partial_credit
from awb.verification.security_scanner import count_security_issues
from awb.verification.test_runner import run_tests

log = logging.getLogger(__name__)
_console = Console()

# Tasks scoring below this % are decisive failures; no need to re-run
_ADAPTIVE_RERUN_MIN = 60

# Progressive mode thresholds
_PROGRESSIVE_EASY_MIN_PASS_RATE = 0.40
_PROGRESSIVE_MEDIUM_MIN_PASS_RATE = 0.20


class BenchmarkRunner:
    def __init__(
        self,
        tool: str,
        tasks: list[TaskDefinition],
        runs: int = 3,
        parallel: bool = False,
        timeout_override: int | None = None,
        workflow: WorkflowInfo | None = None,
        resume: bool = False,
        concurrency: int = 4,
        adaptive: bool = False,
        progressive: bool = False,
        use_uv: bool = False,
    ) -> None:
        self.tool = tool
        self.tasks = tasks
        self.runs = runs
        self.parallel = parallel
        self.timeout_override = timeout_override
        self.workflow = workflow
        self.resume = resume
        self.concurrency = concurrency
        self.adaptive = adaptive
        self.progressive = progressive
        self.repo_manager = RepoManager(use_uv=use_uv)
        self.recorder = ResultRecorder()
        self._environment = RunEnvironment()
        self._adapter = _get_adapter(tool)
        self._run1_times: dict[str, float] = {}  # task_id -> wall clock from run 1

        # Resume: try to find an incomplete run for this tool
        if self.resume:
            existing = self.recorder.find_incomplete_run(tool, len(tasks))
            if existing:
                self._run_id = existing
                _console.print(f"[bold cyan]Resuming run:[/bold cyan] {existing}")
            else:
                self._run_id = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        else:
            self._run_id = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

    def _sort_progressive(self, tasks: list[TaskDefinition]) -> list[TaskDefinition]:
        """Sort tasks by difficulty for progressive mode: easy -> medium -> hard."""
        order = {"easy": 0, "medium": 1, "hard": 2}
        return sorted(tasks, key=lambda t: order.get(t.difficulty, 1))

    def _check_progressive_gate(
        self, results: list[RunResult], difficulty: str
    ) -> tuple[bool, str]:
        """Check if progressive mode should continue after a difficulty tier."""
        tier_results = [r for r in results if self._task_difficulty(r.task_id) == difficulty]
        if not tier_results:
            return True, ""

        pass_rate = sum(1 for r in tier_results if r.outcome.success) / len(tier_results)

        if difficulty == "easy" and pass_rate < _PROGRESSIVE_EASY_MIN_PASS_RATE:
            return False, (
                f"Easy pass rate {pass_rate:.0%} "
                f"< {_PROGRESSIVE_EASY_MIN_PASS_RATE:.0%} threshold. "
                f"Tool not ready for medium/hard."
            )
        if difficulty == "medium" and pass_rate < _PROGRESSIVE_MEDIUM_MIN_PASS_RATE:
            return False, (
                f"Medium pass rate {pass_rate:.0%} "
                f"< {_PROGRESSIVE_MEDIUM_MIN_PASS_RATE:.0%} threshold. "
                f"Skipping hard tasks."
            )
        return True, ""

    def _task_difficulty(self, task_id: str) -> str:
        """Look up difficulty for a task ID."""
        for t in self.tasks:
            if t.id == task_id:
                return t.difficulty
        return "medium"

    def _adaptive_timeout(self, task: TaskDefinition) -> int:
        """Compute timeout, tightening for runs 2+ based on run 1 actuals."""
        base = self.timeout_override or task.constraints.timeout_seconds
        actual = self._run1_times.get(task.id)
        if actual is not None:
            # Tighten to 2x actual time, but never below 60s
            return max(60, min(base, int(actual * 2)))
        return base

    async def run_all(self, on_task_complete=None) -> list[RunResult]:
        """Run all tasks for the configured number of runs."""
        results: list[RunResult] = []
        total_tasks = len(self.tasks) * self.runs
        completed = 0
        passed = 0
        run_start = time.monotonic()

        # Tasks eligible for re-running in adaptive mode (populated after run 1)
        near_miss_ids: set[str] | None = None
        progressive_stopped = False

        for run_num in range(1, self.runs + 1):
            if progressive_stopped:
                break

            run_id = f"{self._run_id}_run{run_num}"

            # In adaptive mode, only re-run near-miss tasks after run 1
            if self.adaptive and near_miss_ids is not None:
                tasks_this_run = [t for t in self.tasks if t.id in near_miss_ids]
            else:
                tasks_this_run = self.tasks

            # Progressive mode: sort by difficulty
            if self.progressive:
                tasks_this_run = self._sort_progressive(tasks_this_run)

            _console.print(
                f"\n[bold cyan]--- Run {run_num}/{self.runs} ---[/bold cyan]  "
                f"({len(tasks_this_run)} tasks, saving to results/runs/{run_id}/)"
            )

            if self.parallel:
                run_results = await self._run_parallel(
                    tasks_this_run, run_id, run_num, total_tasks, on_task_complete
                )
            else:
                run_results = await self._run_sequential(
                    tasks_this_run,
                    run_id,
                    run_num,
                    total_tasks,
                    completed,
                    passed,
                    run_start,
                    on_task_complete,
                )

            run_passed = sum(1 for r in run_results if r.outcome.success)
            run_completed = len(run_results)
            completed += run_completed
            passed += run_passed

            run_pct = run_passed / run_completed * 100 if run_completed else 0
            _console.print(
                f"  [bold]Run {run_num} complete:[/bold] "
                f"{run_passed}/{run_completed} passed ({run_pct:.0f}%)"
            )

            results.extend(run_results)

            # Record run 1 times for adaptive timeout tightening
            if run_num == 1:
                for r in run_results:
                    self._run1_times[r.task_id] = r.metrics.wall_clock_seconds

            # After run 1, classify decisive vs near-miss for adaptive mode
            if self.adaptive and run_num == 1:
                decisive = []
                near_miss = []
                for r in run_results:
                    max_pts = r.outcome.partial_credit_max
                    score = r.outcome.partial_credit_score
                    pct = (score / max_pts * 100) if max_pts else 0
                    if score == 0 or score == max_pts or pct < _ADAPTIVE_RERUN_MIN:
                        decisive.append(r.task_id)
                    else:
                        near_miss.append(r.task_id)
                near_miss_ids = set(near_miss)
                _console.print(
                    f"  [dim]Adaptive: {len(decisive)} decisive (skipped), "
                    f"{len(near_miss)} near-miss (re-running)[/dim]"
                )

            # Progressive mode gates
            if self.progressive and run_num == 1:
                for diff in ("easy", "medium"):
                    should_continue, msg = self._check_progressive_gate(run_results, diff)
                    if not should_continue:
                        _console.print(f"\n  [yellow]Progressive stop:[/yellow] {msg}")
                        progressive_stopped = True
                        break

        total_elapsed = (time.monotonic() - run_start) / 60
        _console.print(
            f"\n[bold]All runs complete:[/bold] {passed}/{completed} passed in {total_elapsed:.0f}m"
        )
        return results

    async def _run_sequential(
        self,
        tasks: list[TaskDefinition],
        run_id: str,
        run_num: int,
        total_tasks: int,
        completed_before: int,
        passed_before: int,
        run_start: float,
        on_task_complete=None,
    ) -> list[RunResult]:
        results = []
        run_passed = 0
        run_completed = 0
        completed = completed_before
        passed = passed_before

        for task in tasks:
            log.info("Run %d/%d - Task %s", run_num, self.runs, task.id)

            # Resume: skip if already recorded
            if self.resume and self.recorder.has_result(run_id, task.id, self.tool):
                cached = self.recorder.load_single(run_id, task.id, self.tool)
                if cached is None:
                    continue
                _console.print(
                    f"  [{completed + 1}/{total_tasks}] {task.id} ({task.difficulty})"
                    f" [dim][SKIP][/dim]"
                )
                completed += 1
                run_completed += 1
                if cached.outcome.success:
                    passed += 1
                    run_passed += 1
                results.append(cached)
                continue

            _console.print(
                f"  [{completed + 1}/{total_tasks}] {task.id} ({task.difficulty}) ...",
                end="",
            )

            task_start = time.monotonic()
            result = await self.run_single(task, run_id=run_id, run_num=run_num)
            elapsed = time.monotonic() - task_start

            completed += 1
            run_completed += 1
            success = result.outcome.success
            if success:
                passed += 1
                run_passed += 1

            score = result.outcome.partial_credit_score
            max_score = result.outcome.partial_credit_max
            status = "[green]PASS[/green]" if success else "[red]FAIL[/red]"
            cost = result.cost.estimated_cost_usd

            avg_time = (time.monotonic() - run_start) / completed
            remaining = total_tasks - completed
            eta_min = (avg_time * remaining) / 60

            _console.print(
                f" {status}  {score}/{max_score}  "
                f"{elapsed:.0f}s  ${cost:.2f}  "
                f"[dim](run: {run_passed}/{run_completed} | "
                f"total: {passed}/{completed} | "
                f"ETA: {eta_min:.0f}m)[/dim]"
            )

            if on_task_complete:
                on_task_complete(result)
            results.append(result)

        return results

    async def _run_parallel(
        self,
        tasks: list[TaskDefinition],
        run_id: str,
        run_num: int,
        total_tasks: int,
        on_task_complete=None,
    ) -> list[RunResult]:
        sem = asyncio.Semaphore(self.concurrency)

        async def _run_bounded(task: TaskDefinition) -> RunResult:
            async with sem:
                return await self.run_single(task, run_id=run_id, run_num=run_num)

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=_console,
        ) as progress:
            bar = progress.add_task(f"Run {run_num}", total=len(tasks))

            async def _tracked(task: TaskDefinition) -> RunResult:
                result = await _run_bounded(task)
                progress.advance(bar)
                if on_task_complete:
                    on_task_complete(result)
                return result

            results = await asyncio.gather(*[_tracked(t) for t in tasks], return_exceptions=True)
            # Filter out exceptions from failed tasks
            valid_results = []
            for r in results:
                if isinstance(r, BaseException):
                    log.error("Parallel task failed: %s", r)
                else:
                    valid_results.append(r)
            results = valid_results

        return list(results)

    async def run_single(
        self,
        task: TaskDefinition,
        run_id: str | None = None,
        run_num: int = 1,
    ) -> RunResult:
        """Execute a single task through the full benchmark lifecycle."""
        run_id = run_id or self._run_id
        timeout = self._adaptive_timeout(task) if run_num > 1 else (
            self.timeout_override or task.constraints.timeout_seconds
        )
        workspace: Path | None = None

        collector = MetricCollector()
        outcome = RunOutcome(success=False, partial_credit_score=0, partial_credit_max=0)
        quality = RunQuality()

        # Token budget callback for streaming enforcement
        budget_exceeded = False

        def _on_event(event: dict) -> bool | None:
            nonlocal budget_exceeded
            collector.parse_stream_event(event)
            # Check token budget if set
            max_in = task.constraints.max_input_tokens
            max_out = task.constraints.max_output_tokens
            if max_in > 0 and collector._input_tokens > max_in:
                budget_exceeded = True
                log.warning("Task %s exceeded input token budget (%d > %d)",
                            task.id, collector._input_tokens, max_in)
                return False
            if max_out > 0 and collector._output_tokens > max_out:
                budget_exceeded = True
                log.warning("Task %s exceeded output token budget (%d > %d)",
                            task.id, collector._output_tokens, max_out)
                return False
            return None

        try:
            # 1. Prepare workspace (run_id scopes the path for concurrent safety)
            workspace = await self.repo_manager.prepare(task, run_id=run_id)

            # 2. Baseline lint/security counts
            baseline_lint = await _count_baseline("lint", task, workspace)
            baseline_security = await _count_baseline("security", task, workspace)

            # 3. Run the tool with streaming event callback
            collector.start()
            tool_result = await run_with_timeout(
                self._adapter.execute(
                    prompt=task.issue_description,
                    workspace=workspace,
                    max_turns=task.constraints.max_iterations,
                    timeout_seconds=timeout,
                    on_event=_on_event,
                ),
                timeout_seconds=timeout,
                task_id=task.id,
            )
            collector.stop()

            # Parse any remaining stream events not yet processed
            # (for adapters that don't support streaming callbacks)
            if not hasattr(self._adapter, '_streams_events_inline'):
                for event in tool_result.stream_events:
                    collector.parse_stream_event(event)

            # 4. Verification — save outputs to run log directory
            run_dir = self.recorder.results_dir / run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            tests_passed, test_output = await run_tests(
                task.verification.test_commands, workspace
            )
            if test_output:
                log_path = run_dir / f"{task.id}_{self.tool}.log"
                log_path.write_text(test_output)

            earned, max_pts, breakdown = await evaluate_partial_credit(
                task.verification.partial_credit, workspace, log_dir=run_dir
            )

            # 5. Quality deltas
            post_lint = await count_lint_issues(task.verification.lint_commands, workspace)
            post_security = await count_security_issues(
                task.verification.security_commands, workspace
            )
            quality = RunQuality(
                lint_delta=post_lint - baseline_lint,
                security_delta=post_security - baseline_security,
                test_regressions=0 if tests_passed else 1,
            )

            # 6. File change stats
            metrics = collector.to_metrics()
            metrics.files_modified = len(self.repo_manager.get_modified_files(workspace))
            metrics.lines_changed = self.repo_manager.get_lines_changed(workspace)

            outcome = RunOutcome(
                success=tests_passed and earned == max_pts,
                partial_credit_score=earned,
                partial_credit_max=max_pts,
                breakdown=breakdown,
            )

        except TaskTimeoutError:
            collector.stop()
            log.warning("Task %s timed out after %ds", task.id, timeout)

        except RuntimeError as exc:
            collector.stop()
            log.error("Task %s setup failed: %s", task.id, exc)
            _console.print(f"  [red]setup_error:[/red] {exc}")

        except NotImplementedError as exc:
            collector.stop()
            import click

            raise click.UsageError(f"Adapter not implemented: {exc}") from exc

        except Exception:
            collector.stop()
            log.exception("Task %s failed with unexpected error", task.id)
            _console.print(f"  [red]error:[/red] {task.id} — see log for details")
            print(f"Task {task.id} failed unexpectedly — check logs", file=sys.stderr)

        finally:
            metrics = collector.to_metrics()
            if workspace:
                await self.repo_manager.cleanup(workspace)

        result = RunResult(
            task_id=task.id,
            tool=self.tool,
            tool_version=self._adapter.get_version(),
            model=getattr(self._adapter, "model", "unknown"),
            run_id=run_id,
            timestamp=datetime.now(UTC).isoformat(),
            outcome=outcome,
            metrics=metrics,
            cost=collector.to_cost(),
            quality=quality,
            environment=self._environment,
            workflow=self.workflow,
        )

        self.recorder.save(result)
        return result


def _get_adapter(name: str):
    """Import and instantiate adapter by name."""
    from awb.adapters.registry import get_adapter

    return get_adapter(name)


async def _count_baseline(kind: str, task: TaskDefinition, workspace: Path) -> int:
    """Count baseline lint or security issues before tool runs."""
    try:
        if kind == "lint":
            return await count_lint_issues(task.verification.lint_commands, workspace)
        elif kind == "security":
            return await count_security_issues(task.verification.security_commands, workspace)
    except Exception as exc:
        log.debug("Baseline %s count failed: %s", kind, exc)
    return 0
