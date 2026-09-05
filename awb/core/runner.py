"""Main benchmark orchestrator."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from awb.core.config import (
    TASKS_DIR,
    RunEnvironment,
    RunExecution,
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
from awb.scoring.integrity import compute_task_set_hash
from awb.trace import TraceWriter
from awb.trace.translate import TraceTranslator
from awb.verification.lint_checker import count_lint_issues, measure_lint_issues
from awb.verification.partial_credit import evaluate_partial_credit
from awb.verification.security_scanner import count_security_issues, measure_security_issues
from awb.verification.test_runner import run_tests

log = logging.getLogger(__name__)
_console = Console()

# Tasks scoring below this % are decisive failures; no need to re-run
_ADAPTIVE_RERUN_MIN = 60

# Progressive mode thresholds
_PROGRESSIVE_EASY_MIN_PASS_RATE = 0.40
_PROGRESSIVE_MEDIUM_MIN_PASS_RATE = 0.20

# Fan-out used when --parallel is passed without an explicit -j value.
_DEFAULT_PARALLEL_FANOUT = 4


def resolve_parallelism(parallel: bool, concurrency: int) -> tuple[bool, int]:
    """Decide whether to run in parallel and at what concurrency.

    `-j N` (N>1) is itself a request to parallelize, so it no longer silently
    no-ops when `--parallel` is absent. `--parallel` on its own picks a sane
    fan-out. Default (sequential) is preserved: parallel=False, concurrency=1.
    """
    if parallel and concurrency <= 1:
        concurrency = _DEFAULT_PARALLEL_FANOUT
    enabled = parallel or concurrency > 1
    return enabled, concurrency


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
        tasks_dir: Path | None = None,
        experiment_timeout_seconds: int | None = None,
        setup_timeout_seconds: int = 900,
        verification_timeout_seconds: int = 600,
        execution_mode: str = "host",
        container_image: str = "",
    ) -> None:
        self.tool = tool
        self.tasks = tasks
        self.runs = runs
        self.parallel, concurrency = resolve_parallelism(parallel, concurrency)
        self.timeout_override = timeout_override
        self.workflow = workflow
        self.resume = resume
        self.concurrency = concurrency
        self.adaptive = adaptive
        self.progressive = progressive
        self.experiment_timeout_seconds = experiment_timeout_seconds
        self.setup_timeout_seconds = setup_timeout_seconds
        self.verification_timeout_seconds = verification_timeout_seconds
        self.execution_mode = execution_mode
        self.container_image = container_image
        self._experiment_deadline: float | None = None
        self.repo_manager = RepoManager(use_uv=use_uv)
        self.recorder = ResultRecorder()
        self._environment = RunEnvironment()
        self._adapter = _get_adapter(tool)
        self._run1_times: dict[str, float] = {}  # task_id -> wall clock from run 1
        # Compute once per runner so every saved result pins the same task set.
        # Hash the directory the tasks were actually loaded from: a private
        # --tasks-dir run stamped with the public hash would defeat drift's
        # task_set_hash_mismatch guard exactly when it matters.
        self._task_set_hash = compute_task_set_hash(Path(str(tasks_dir or TASKS_DIR)))

        # Resume: try to find an incomplete run for this tool
        if self.resume:
            declared_model = (self.workflow.model if self.workflow else "") or getattr(
                self._adapter, "model", ""
            )
            if declared_model == "unknown":
                declared_model = ""
            identity_by_task = {}
            for task in tasks:
                identity = self._identity_fields(task, None)
                identity_by_task[task.id] = {
                    "task_definition_hash": identity["task_definition_hash"],
                    "evaluator_version": identity["evaluator_version"],
                    "effective_config_hash": identity["effective_config_hash"],
                    "adapter_version": identity["adapter_version"],
                    "model": declared_model,
                    "execution_mode": identity["execution_mode"],
                    "environment_fingerprint": identity["environment_fingerprint"],
                    "budget_fingerprint": identity["budget_fingerprint"],
                    "cohort_manifest": identity["cohort_manifest"],
                }
            existing = self.recorder.find_incomplete_run(
                tool,
                task_ids=[task.id for task in tasks],
                requested_runs=runs,
                task_set_hash=self._task_set_hash,
                identity_by_task=identity_by_task,
            )
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
        if self.experiment_timeout_seconds:
            self._experiment_deadline = run_start + self.experiment_timeout_seconds

        # Tasks eligible for re-running in adaptive mode (populated after run 1)
        near_miss_ids: set[str] | None = None
        progressive_stopped = False

        for run_num in range(1, self.runs + 1):
            if (
                self._experiment_deadline is not None
                and time.monotonic() >= self._experiment_deadline
            ):
                _console.print(
                    "[yellow]Experiment deadline reached; "
                    "remaining attempts are resumable.[/yellow]"
                )
                break
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

            if self._deadline_reached():
                break

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
            if result.cost.estimated_credits is not None:
                cost = (
                    f"{result.cost.estimated_credits:.2f} cr "
                    f"(${result.cost.estimated_cost_usd:.2f} equiv)"
                )
            else:
                cost = f"${result.cost.estimated_cost_usd:.2f}"

            avg_time = (time.monotonic() - run_start) / completed
            remaining = total_tasks - completed
            eta_min = (avg_time * remaining) / 60

            _console.print(
                f" {status}  {score}/{max_score}  "
                f"{elapsed:.0f}s  {cost}  "
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
        cached_results: list[RunResult] = []
        pending_tasks: list[TaskDefinition] = []
        for task in tasks:
            cached = (
                self.recorder.load_single(run_id, task.id, self.tool)
                if getattr(self, "resume", False)
                else None
            )
            if cached is None:
                pending_tasks.append(task)
            else:
                cached_results.append(cached)

        sem = asyncio.Semaphore(self.concurrency)

        async def _run_bounded(task: TaskDefinition) -> RunResult | None:
            async with sem:
                if self._deadline_reached():
                    return None
                return await self.run_single(task, run_id=run_id, run_num=run_num)

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=_console,
        ) as progress:
            bar = progress.add_task(
                f"Run {run_num}", total=len(tasks), completed=len(cached_results)
            )

            async def _tracked(task: TaskDefinition) -> RunResult | None:
                result = await _run_bounded(task)
                if result is not None:
                    progress.advance(bar)
                if result is not None and on_task_complete:
                    on_task_complete(result)
                return result

            gathered = await asyncio.gather(
                *[_tracked(t) for t in pending_tasks], return_exceptions=True
            )

        # Pair each result with its task (gather preserves order) so a raised
        # exception becomes a recorded FAIL instead of vanishing. Stub/usage
        # errors abort the whole run, matching the sequential path.
        import click

        valid_results: list[RunResult] = list(cached_results)
        for task, r in zip(pending_tasks, gathered, strict=True):
            if r is None:
                continue
            if isinstance(r, click.UsageError | NotImplementedError):
                raise r
            if isinstance(r, BaseException):
                log.error("Parallel task %s failed: %s", task.id, r)
                valid_results.append(self._failed_result(task, r))
            else:
                valid_results.append(r)

        return valid_results

    def _deadline_reached(self) -> bool:
        deadline = getattr(self, "_experiment_deadline", None)
        return deadline is not None and time.monotonic() >= deadline

    def _failed_result(self, task: TaskDefinition, exc: BaseException) -> RunResult:
        """Build (and persist) a FAIL result for a task that raised in parallel.

        Mirrors the in-task error capture in run_single so a crash on the
        parallel path is still surfaced as a scored failure with a traceback.
        """
        import traceback as _tb

        from awb.core.config import RunCost, RunError, RunMetrics

        tb_lines = _tb.format_exception(type(exc), exc, exc.__traceback__)
        tb_tail = "".join(tb_lines[-8:]) if tb_lines else ""
        result = RunResult(
            task_id=task.id,
            tool=self.tool,
            run_id=getattr(self, "_run_id", "unknown"),
            timestamp=datetime.now(UTC).isoformat(),
            outcome=RunOutcome(
                success=False,
                partial_credit_score=0,
                partial_credit_max=0,
                error=RunError(
                    exc_type=type(exc).__name__,
                    exc_message=str(exc)[:500],
                    traceback_tail=tb_tail[-2000:],
                ),
            ),
            metrics=RunMetrics(),
            cost=RunCost(),
            quality=RunQuality(),
            environment=getattr(self, "_environment", RunEnvironment()),
            workflow=getattr(self, "workflow", None),
            task_set_hash=getattr(self, "_task_set_hash", ""),
        )
        recorder = getattr(self, "recorder", None)
        if recorder is not None:
            recorder.save(result)
        return result

    async def run_single(
        self,
        task: TaskDefinition,
        run_id: str | None = None,
        run_num: int = 1,
    ) -> RunResult:
        """Execute a single task through the full benchmark lifecycle."""
        run_id = run_id or self._run_id
        timeout = (
            self._adaptive_timeout(task)
            if run_num > 1
            else (self.timeout_override or task.constraints.timeout_seconds)
        )
        workspace: Path | None = None
        baseline_changes: dict[str, bytes | None] = {}
        baseline_snapshot_captured = False
        agent_metrics_captured = False
        identity_fields: dict = {}

        # Fail-fast for stub adapters: refuse before provisioning a workspace
        # rather than after, which used to waste ~30s on the first task.
        if getattr(self._adapter, "is_stub", False):
            import click as _click

            raise _click.UsageError(
                f"Adapter '{self._adapter.name}' is a stub. "
                "Install the underlying CLI and flip `is_stub = False` "
                "in the adapter class to enable."
            )

        collector = MetricCollector(pricing=self._adapter.get_model_pricing())
        tool_model = getattr(self._adapter, "model", "") or "unknown"
        outcome = RunOutcome(success=False, partial_credit_score=0, partial_credit_max=0)
        quality = RunQuality()
        execution = RunExecution(status="running", stage="prepare")
        metrics = collector.to_metrics()

        # Trace writer — open before adapter runs, closed in finally
        run_dir = self.recorder.results_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trace_rel = f"{task.id}_{self.tool}.trace.jsonl"
        trace_path = run_dir / trace_rel
        trace_writer = TraceWriter(trace_path)
        # Workspace root is set once the repo is prepared (below) so file spans
        # carry repo-relative paths that match the task's files_to_examine.
        translator = TraceTranslator(trace_writer, task.id)

        # Token budget callback for streaming enforcement
        budget_exceeded = False

        def _on_event(event: dict) -> bool | None:
            nonlocal budget_exceeded
            collector.parse_stream_event(event)
            translator.handle(event)
            # Check token budget if set
            max_in = task.constraints.max_input_tokens
            max_out = task.constraints.max_output_tokens
            if max_in > 0 and collector._input_tokens > max_in:
                budget_exceeded = True
                log.warning(
                    "Task %s exceeded input token budget (%d > %d)",
                    task.id,
                    collector._input_tokens,
                    max_in,
                )
                return False
            if max_out > 0 and collector._output_tokens > max_out:
                budget_exceeded = True
                log.warning(
                    "Task %s exceeded output token budget (%d > %d)",
                    task.id,
                    collector._output_tokens,
                    max_out,
                )
                return False
            return None

        try:
            # 1. Prepare workspace (run_id scopes the path for concurrent safety)
            workspace = await self._run_stage(
                self.repo_manager.prepare(task, run_id=run_id),
                getattr(self, "setup_timeout_seconds", 900),
                task.id,
                "setup_timeout",
            )
            identity_fields = self._identity_fields(task, workspace)
            # File-edit spans now relativize paths against the real workspace.
            translator.workspace_root = str(workspace)

            # 2. Baseline quality measurements. Capture the change snapshot
            # afterward so caches created by baseline checks are not agent edits.
            execution.stage = "baseline"
            baseline_tests_passed, baseline_test_output = await self._run_stage(
                run_tests(task.verification.test_commands, workspace),
                getattr(self, "verification_timeout_seconds", 600),
                task.id,
                "baseline_test_timeout",
            )
            baseline_test_status = _test_measurement_status(
                task.verification.test_commands, baseline_test_output
            )
            baseline_lint, baseline_lint_status = await self._run_stage(
                measure_lint_issues(task.verification.lint_commands, workspace),
                getattr(self, "verification_timeout_seconds", 600),
                task.id,
                "baseline_lint_timeout",
            )
            baseline_security, baseline_security_status = await self._run_stage(
                measure_security_issues(task.verification.security_commands, workspace),
                getattr(self, "verification_timeout_seconds", 600),
                task.id,
                "baseline_security_timeout",
            )
            baseline_changes = self.repo_manager.capture_change_snapshot(workspace)
            baseline_snapshot_captured = True

            # 3. Run the tool with streaming event callback
            execution.stage = "agent"
            collector.start()
            agent_timeout = self._stage_timeout(timeout)
            tool_result = await run_with_timeout(
                self._adapter.execute(
                    prompt=task.issue_description,
                    workspace=workspace,
                    max_turns=task.constraints.max_iterations,
                    timeout_seconds=agent_timeout,
                    on_event=_on_event,
                ),
                timeout_seconds=agent_timeout,
                task_id=task.id,
            )
            if tool_result.model:
                tool_model = tool_result.model
            collector.stop()
            execution.tool_success = tool_result.success
            execution.tool_exit_code = tool_result.exit_code
            if not tool_result.success:
                execution.status = "timed_out" if tool_result.exit_code == 124 else "failed"
                execution.termination_reason = (
                    "agent_timeout" if tool_result.exit_code == 124 else "tool_error"
                )

            # Parse any remaining stream events not yet processed
            # (for adapters that don't support streaming callbacks)
            if not hasattr(self._adapter, "_streams_events_inline"):
                for event in tool_result.stream_events:
                    collector.parse_stream_event(event)

            # Capture only the agent's patch, before verification commands can
            # create their own artifacts. The baseline excludes task overlays
            # and setup output that were already present before Codex ran.
            metrics = collector.to_metrics()
            metrics.files_modified = len(
                self.repo_manager.get_modified_files_since(workspace, baseline_changes)
            )
            metrics.lines_changed = self.repo_manager.get_lines_changed_since(
                workspace, baseline_changes
            )
            agent_metrics_captured = True

            # 4. Verification — save outputs to run log directory
            run_dir = self.recorder.results_dir / run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            execution.stage = "verification"
            tests_passed, test_output = await self._run_stage(
                run_tests(task.verification.test_commands, workspace),
                getattr(self, "verification_timeout_seconds", 600),
                task.id,
                "verification_timeout",
            )
            if test_output:
                log_path = run_dir / f"{task.id}_{self.tool}.log"
                log_path.write_text(test_output)

            earned, max_pts, breakdown = await self._run_stage(
                evaluate_partial_credit(
                    task.verification.partial_credit, workspace, log_dir=run_dir
                ),
                getattr(self, "verification_timeout_seconds", 600),
                task.id,
                "partial_credit_timeout",
            )

            # 5. Quality deltas
            post_lint, post_lint_status = await self._run_stage(
                measure_lint_issues(task.verification.lint_commands, workspace),
                getattr(self, "verification_timeout_seconds", 600),
                task.id,
                "lint_timeout",
            )
            post_security, post_security_status = await self._run_stage(
                measure_security_issues(task.verification.security_commands, workspace),
                getattr(self, "verification_timeout_seconds", 600),
                task.id,
                "security_timeout",
            )
            post_test_status = _test_measurement_status(
                task.verification.test_commands, test_output
            )
            test_regressions = int(baseline_tests_passed and not tests_passed)
            quality = RunQuality(
                lint_delta=post_lint - baseline_lint,
                security_delta=post_security - baseline_security,
                test_regressions=test_regressions,
                lint_status=_delta_measurement_status(
                    baseline_lint_status, post_lint_status, post_lint - baseline_lint
                ),
                security_status=_delta_measurement_status(
                    baseline_security_status,
                    post_security_status,
                    post_security - baseline_security,
                ),
                test_regressions_status=_delta_measurement_status(
                    baseline_test_status, post_test_status, test_regressions
                ),
            )

            outcome = RunOutcome(
                success=tests_passed and earned == max_pts,
                partial_credit_score=earned,
                partial_credit_max=max_pts,
                breakdown=breakdown,
            )
            execution.stage = "complete"
            if execution.status == "running":
                execution.status = "completed"

        except TaskTimeoutError:
            collector.stop()
            log.warning("Task %s timed out after %ds", task.id, timeout)
            execution.status = "timed_out"
            execution.termination_reason = (
                "experiment_timeout"
                if getattr(self, "_experiment_deadline", None) is not None
                and time.monotonic() >= self._experiment_deadline
                else f"{execution.stage}_timeout"
            )

        except RuntimeError as exc:
            collector.stop()
            log.error("Task %s setup failed: %s", task.id, exc)
            _console.print(f"  [red]setup_error:[/red] {exc}")
            execution.status = "failed"
            execution.termination_reason = "setup_error"

        except NotImplementedError as exc:
            collector.stop()
            import click

            raise click.UsageError(f"Adapter not implemented: {exc}") from exc

        except Exception as exc:
            collector.stop()
            log.exception("Task %s failed with unexpected error", task.id)
            import traceback as _tb

            from awb.core.config import RunError

            tb_lines = _tb.format_exception(type(exc), exc, exc.__traceback__)
            tb_tail = "".join(tb_lines[-8:]) if tb_lines else ""
            outcome = RunOutcome(
                success=False,
                partial_credit_score=0,
                partial_credit_max=0,
                error=RunError(
                    exc_type=type(exc).__name__,
                    exc_message=str(exc)[:500],
                    traceback_tail=tb_tail[-2000:],
                ),
            )
            execution.status = "failed"
            execution.termination_reason = "unexpected_error"
            _console.print(f"  [red]error:[/red] {task.id} {type(exc).__name__}: {str(exc)[:120]}")
            print(
                f"Task {task.id} failed: {type(exc).__name__}: {str(exc)[:200]}",
                file=sys.stderr,
            )

        finally:
            # Preserve the diff-derived file metrics populated after a
            # successful run. Rebuilding RunMetrics here used to erase them
            # immediately before the result was saved.
            final_metrics = collector.to_metrics()
            metrics.wall_clock_seconds = final_metrics.wall_clock_seconds
            metrics.iteration_count = final_metrics.iteration_count
            metrics.human_interventions = final_metrics.human_interventions
            metrics.tool_calls = final_metrics.tool_calls
            trace_writer.close()
            if workspace:
                if baseline_snapshot_captured and not agent_metrics_captured:
                    # A timeout or adapter exception may still leave a partial
                    # patch. Measure it before cleanup rather than reporting a
                    # false zero for review burden.
                    with contextlib.suppress(Exception):
                        metrics.files_modified = len(
                            self.repo_manager.get_modified_files_since(workspace, baseline_changes)
                        )
                        metrics.lines_changed = self.repo_manager.get_lines_changed_since(
                            workspace, baseline_changes
                        )
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self.repo_manager.cleanup(workspace), timeout=30)

        # Trace path is recorded relative to the run dir so result JSON stays
        # portable across machines.
        recorded_trace_path = trace_rel if trace_path.exists() else ""

        # Stamp adapter version onto the environment record so a result
        # carries enough provenance for an independent re-run.
        env_with_adapter = RunEnvironment(
            os=self._environment.os,
            hardware=self._environment.hardware,
            python_version=self._environment.python_version,
            awb_version=self._environment.awb_version,
            adapter_version=self._adapter.get_version(),
            pip_freeze_hash=self._environment.pip_freeze_hash,
        )

        result = RunResult(
            task_id=task.id,
            tool=self.tool,
            tool_version=self._adapter.get_version(),
            model=tool_model,
            run_id=run_id,
            timestamp=datetime.now(UTC).isoformat(),
            outcome=outcome,
            metrics=metrics,
            cost=collector.to_cost(),
            quality=quality,
            environment=env_with_adapter,
            workflow=self.workflow,
            task_set_hash=self._task_set_hash,
            trace_path=recorded_trace_path,
            execution=execution,
            **(identity_fields or self._identity_fields(task, None)),
        )

        self.recorder.save(result)
        return result

    async def _run_stage(self, coro, configured_timeout: int, task_id: str, reason: str):
        del reason
        timeout = self._stage_timeout(configured_timeout)
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError:
            raise TaskTimeoutError(task_id, int(timeout)) from None

    def _stage_timeout(self, configured_timeout: int | float) -> float:
        timeout = float(configured_timeout)
        deadline = getattr(self, "_experiment_deadline", None)
        if deadline is not None:
            timeout = min(timeout, max(0.001, deadline - time.monotonic()))
        return timeout

    def _identity_fields(self, task: TaskDefinition, workspace: Path | None) -> dict:
        task_hash = _stable_hash(asdict(task))
        adapter_version = self._adapter.get_version()
        config_hash = _stable_hash(
            {
                "adapter": self._adapter.get_config_hash(),
                "workflow": asdict(self.workflow) if self.workflow else None,
            }
        )
        selected_tasks = sorted(getattr(self, "tasks", [task]), key=lambda item: item.id)
        selected_task_definition_hashes = {
            item.id: _stable_hash(asdict(item)) for item in selected_tasks
        }
        task_budgets = {
            item.id: {
                "timeout_seconds": self.timeout_override or item.constraints.timeout_seconds,
                "max_iterations": item.constraints.max_iterations,
                "max_input_tokens": item.constraints.max_input_tokens,
                "max_output_tokens": item.constraints.max_output_tokens,
            }
            for item in selected_tasks
        }
        budget_hash = _stable_hash(
            {
                "runs": getattr(self, "runs", 1),
                "tasks": task_budgets,
                "setup_timeout": getattr(self, "setup_timeout_seconds", 900),
                "verification_timeout": getattr(self, "verification_timeout_seconds", 600),
                "experiment_timeout": getattr(self, "experiment_timeout_seconds", None),
                "adaptive": getattr(self, "adaptive", False),
                "progressive": getattr(self, "progressive", False),
            }
        )
        environment_hash = _stable_hash(
            {
                **asdict(self._environment),
                "adapter_version": adapter_version,
                "execution_mode": getattr(self, "execution_mode", "host"),
                "container_image": getattr(self, "container_image", ""),
            }
        )
        loaded = []
        instruction_hashes = {}
        if workspace:
            candidates: tuple[str, ...] = ()
            if self.tool == "codex-cli":
                candidates = (
                    ("AGENTS.override.md",)
                    if (workspace / "AGENTS.override.md").is_file()
                    else ("AGENTS.md",)
                )
            elif self.tool.startswith("claude-code"):
                candidates = (".claude/CLAUDE.md", "CLAUDE.md")
            for relative in candidates:
                if (workspace / relative).is_file():
                    loaded.append(relative)
                    instruction_hashes[relative] = hashlib.sha256(
                        (workspace / relative).read_bytes()
                    ).hexdigest()
        cohort_id = _stable_hash(
            {
                "task_set_hash": self._task_set_hash,
                "selected_task_ids": [item.id for item in selected_tasks],
                "selected_task_definition_hashes": selected_task_definition_hashes,
                "effective_config_hash": config_hash,
                "environment_fingerprint": environment_hash,
                "budget_fingerprint": budget_hash,
            }
        )
        return {
            "task_definition_hash": task_hash,
            "evaluator_version": self._environment.awb_version,
            "effective_config_hash": config_hash,
            "adapter_version": adapter_version,
            "execution_mode": getattr(self, "execution_mode", "host"),
            "environment_fingerprint": environment_hash,
            "budget_fingerprint": budget_hash,
            "cohort_id": cohort_id,
            "loaded_instruction_files": loaded,
            "allowed_edit_paths": list(task.allowed_edit_paths),
            "effective_input_manifest": {
                "task_definition_hash": task_hash,
                "prompt_hash": hashlib.sha256(task.issue_description.encode()).hexdigest(),
                "instruction_hashes": instruction_hashes,
                "allowed_edit_paths": list(task.allowed_edit_paths),
                "task_budget": task_budgets[task.id],
            },
            "environment_manifest": {
                **asdict(self._environment),
                "adapter_version": adapter_version,
                "execution_mode": getattr(self, "execution_mode", "host"),
                "container_image": getattr(self, "container_image", ""),
                "ambient_credentials_forwarded": (
                    False if getattr(self, "execution_mode", "host") == "container" else None
                ),
            },
            "cohort_manifest": {
                "cohort_id": cohort_id,
                "selected_task_ids": [item.id for item in selected_tasks],
                "selected_task_definition_hashes": selected_task_definition_hashes,
                "requested_repeats": getattr(self, "runs", 1),
                "task_set_hash": self._task_set_hash,
                "task_definition_hash": task_hash,
                "effective_config_hash": config_hash,
                "environment_fingerprint": environment_hash,
                "budget_fingerprint": budget_hash,
            },
        }


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


def _stable_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _test_measurement_status(commands: list[str], output: str) -> str:
    if not commands:
        return "missing"
    if "[TIMEOUT" in output or "[command not found]" in output:
        return "failed"
    return "measured_clean"


def _delta_measurement_status(before: str, after: str, delta: int) -> str:
    statuses = {before, after}
    if "failed" in statuses:
        return "failed"
    if "missing" in statuses:
        return "missing"
    return "measured_findings" if delta > 0 else "measured_clean"
