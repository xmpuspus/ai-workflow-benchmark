"""Main benchmark orchestrator."""
from __future__ import annotations

import asyncio
import logging
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

log = logging.getLogger(__name__)
_console = Console()

# Tasks scoring below this % are decisive failures; no need to re-run
_ADAPTIVE_RERUN_MIN = 60


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
        self.repo_manager = RepoManager()
        self.recorder = ResultRecorder()

        # Resume: try to find an incomplete run for this tool
        if self.resume:
            existing = self.recorder.find_incomplete_run(tool, len(tasks))
            if existing:
                self._run_id = existing
                _console.print(
                    f"[bold cyan]Resuming run:[/bold cyan] {existing}"
                )
            else:
                self._run_id = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        else:
            self._run_id = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

    async def run_all(self) -> list[RunResult]:
        """Run all tasks for the configured number of runs."""
        results: list[RunResult] = []
        total_tasks = len(self.tasks) * self.runs
        completed = 0
        passed = 0
        run_start = time.monotonic()

        # Tasks eligible for re-running in adaptive mode (populated after run 1)
        near_miss_ids: set[str] | None = None

        for run_num in range(1, self.runs + 1):
            run_id = f"{self._run_id}_run{run_num}"

            # In adaptive mode, only re-run near-miss tasks after run 1
            if self.adaptive and near_miss_ids is not None:
                tasks_this_run = [t for t in self.tasks if t.id in near_miss_ids]
            else:
                tasks_this_run = self.tasks

            _console.print(
                f"\n[bold cyan]--- Run {run_num}/{self.runs} ---[/bold cyan]  "
                f"({len(tasks_this_run)} tasks, saving to results/runs/{run_id}/)"
            )

            if self.parallel:
                run_results = await self._run_parallel(tasks_this_run, run_id, run_num, total_tasks)
            else:
                run_results = await self._run_sequential(
                    tasks_this_run, run_id, run_num, total_tasks, completed, passed, run_start
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

        total_elapsed = (time.monotonic() - run_start) / 60
        _console.print(
            f"\n[bold]All runs complete:[/bold] "
            f"{passed}/{completed} passed in {total_elapsed:.0f}m"
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
            result = await self.run_single(task, run_id=run_id)
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

            results.append(result)

        return results

    async def _run_parallel(
        self,
        tasks: list[TaskDefinition],
        run_id: str,
        run_num: int,
        total_tasks: int,
    ) -> list[RunResult]:
        sem = asyncio.Semaphore(self.concurrency)

        async def _run_bounded(task: TaskDefinition) -> RunResult:
            async with sem:
                return await self.run_single(task, run_id=run_id)

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
                return result

            results = await asyncio.gather(*[_tracked(t) for t in tasks])

        return list(results)

    async def run_single(
        self,
        task: TaskDefinition,
        run_id: str | None = None,
    ) -> RunResult:
        """Execute a single task through the full benchmark lifecycle."""
        run_id = run_id or self._run_id
        timeout = self.timeout_override or task.constraints.timeout_seconds
        workspace: Path | None = None

        collector = MetricCollector()
        outcome = RunOutcome(success=False, partial_credit_score=0, partial_credit_max=0)
        quality = RunQuality()

        try:
            # 1. Prepare workspace (run_id scopes the path for concurrent safety)
            workspace = await self.repo_manager.prepare(task, run_id=run_id)

            # 2. Baseline lint/security counts
            baseline_lint = await _count_baseline("lint", task, workspace)
            baseline_security = await _count_baseline("security", task, workspace)

            # 3. Run the tool
            collector.start()
            adapter = _get_adapter(self.tool)
            tool_result = await run_with_timeout(
                adapter.execute(
                    prompt=task.issue_description,
                    workspace=workspace,
                    max_turns=task.constraints.max_iterations,
                    timeout_seconds=timeout,
                ),
                timeout_seconds=timeout,
                task_id=task.id,
            )
            collector.stop()

            # Parse stream events for metrics
            for event in tool_result.stream_events:
                collector.parse_stream_event(event)

            # 4. Verification
            from awb.verification.lint_checker import count_lint_issues
            from awb.verification.partial_credit import evaluate_partial_credit
            from awb.verification.security_scanner import count_security_issues
            from awb.verification.test_runner import run_tests

            tests_passed, _ = await run_tests(
                task.verification.test_commands, workspace
            )

            earned, max_pts, breakdown = await evaluate_partial_credit(
                task.verification.partial_credit, workspace
            )

            # 5. Quality deltas
            post_lint = await count_lint_issues(
                task.verification.lint_commands, workspace
            )
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

        except Exception:
            collector.stop()
            log.exception("Task %s failed with error", task.id)

        finally:
            metrics = collector.to_metrics()

        # Build result (reuse adapter from try block if available)
        adapter_info = _get_adapter(self.tool)
        result = RunResult(
            task_id=task.id,
            tool=self.tool,
            tool_version=adapter_info.get_version(),
            model=getattr(adapter_info, "model", "unknown"),
            run_id=run_id,
            timestamp=datetime.now(UTC).isoformat(),
            outcome=outcome,
            metrics=metrics,
            cost=collector.to_cost(),
            quality=quality,
            environment=RunEnvironment(),
            workflow=self.workflow,
        )

        self.recorder.save(result)

        # Cleanup
        if workspace:
            await self.repo_manager.cleanup(workspace)

        return result


def _get_adapter(name: str):
    """Import and instantiate adapter by name."""
    from awb.adapters.registry import get_adapter
    return get_adapter(name)


async def _count_baseline(kind: str, task: TaskDefinition, workspace: Path) -> int:
    """Count baseline lint or security issues before tool runs."""
    try:
        if kind == "lint":
            from awb.verification.lint_checker import count_lint_issues
            return await count_lint_issues(task.verification.lint_commands, workspace)
        elif kind == "security":
            from awb.verification.security_scanner import count_security_issues
            return await count_security_issues(
                task.verification.security_commands, workspace
            )
    except Exception as exc:
        log.debug("Baseline %s count failed: %s", kind, exc)
    return 0
