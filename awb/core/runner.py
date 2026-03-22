"""Main benchmark orchestrator."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

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


class BenchmarkRunner:
    def __init__(
        self,
        tool: str,
        tasks: list[TaskDefinition],
        runs: int = 3,
        parallel: bool = False,
        timeout_override: int | None = None,
        workflow: WorkflowInfo | None = None,
    ) -> None:
        self.tool = tool
        self.tasks = tasks
        self.runs = runs
        self.parallel = parallel
        self.timeout_override = timeout_override
        self.workflow = workflow
        self.repo_manager = RepoManager()
        self.recorder = ResultRecorder()
        self._run_id = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

    async def run_all(self) -> list[RunResult]:
        """Run all tasks for the configured number of runs."""
        results: list[RunResult] = []
        for run_num in range(1, self.runs + 1):
            run_id = f"{self._run_id}_run{run_num}"
            for task in self.tasks:
                log.info("Run %d/%d - Task %s", run_num, self.runs, task.id)
                result = await self.run_single(task, run_id=run_id)
                results.append(result)
        return results

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
            # 1. Prepare workspace
            workspace = await self.repo_manager.prepare(task)

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
