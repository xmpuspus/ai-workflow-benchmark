"""Parallelism resolution + parallel-failure recording.

Two audit fixes:
1. `-j N` was a silent no-op: the runner only went parallel when `--parallel`
   was set, so a bare `-j 8` ran sequentially and ignored the value.
2. The parallel path used `gather(return_exceptions=True)` and only log.error'd
   failures, so a task that raised vanished from results with no FAIL record.
"""

from __future__ import annotations

import pytest

from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.runner import BenchmarkRunner, resolve_parallelism


def test_default_is_sequential():
    enabled, conc = resolve_parallelism(parallel=False, concurrency=1)
    assert enabled is False
    assert conc == 1


def test_concurrency_gt_1_enables_parallel():
    enabled, conc = resolve_parallelism(parallel=False, concurrency=8)
    assert enabled is True
    assert conc == 8


def test_parallel_flag_alone_picks_a_fanout():
    enabled, conc = resolve_parallelism(parallel=True, concurrency=1)
    assert enabled is True
    assert conc > 1


def test_parallel_failure_is_recorded_not_dropped(monkeypatch, sample_task):
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.tool = "x"
    runner.runs = 1
    runner.concurrency = 2
    runner.tasks = [sample_task]

    async def _boom(task, run_id=None, run_num=1):
        raise RuntimeError("kaboom")

    runner.run_single = _boom

    import asyncio

    results = asyncio.run(
        runner._run_parallel([sample_task], run_id="r1", run_num=1, total_tasks=1)
    )
    assert len(results) == 1
    assert results[0].outcome.success is False
    assert results[0].task_id == sample_task.id
    assert results[0].outcome.error is not None
    assert "kaboom" in results[0].outcome.error.exc_message


def test_stub_usage_error_still_aborts_parallel(monkeypatch, sample_task):
    import click

    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.tool = "x"
    runner.runs = 1
    runner.concurrency = 2
    runner.tasks = [sample_task]

    async def _stub(task, run_id=None, run_num=1):
        raise click.UsageError("adapter is a stub")

    runner.run_single = _stub

    import asyncio

    with pytest.raises(click.UsageError):
        asyncio.run(runner._run_parallel([sample_task], run_id="r1", run_num=1, total_tasks=1))


class _FakeAdapter(ToolAdapter):
    name = "fake"
    display_name = "Fake"

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=1800, on_event=None):
        return ToolResult(success=True, raw_output="", stream_events=[])

    def check_available(self) -> bool:
        return True

    def get_config_hash(self) -> str:
        return "h"
