"""Regression test for the JSONL append race fix in awb/core/results.py.

POSIX atomic-append only guarantees writes up to PIPE_BUF (~4KB). Result
records can exceed 5KB, so concurrent `--parallel` writers could silently
interleave bytes. The fix wraps writes in fcntl.LOCK_EX. This test asserts
that 100 concurrent ~8KB writes produce 100 valid JSON lines.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from awb.core.config import (
    CriterionResult,
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
)
from awb.core.results import ResultRecorder


def _make_result(idx: int) -> RunResult:
    # Pad breakdown so each record is well above PIPE_BUF.
    breakdown = [
        CriterionResult(
            criterion=f"criterion-{idx}-{i}-" + ("x" * 200),
            points_earned=10.0,
            points_possible=10.0,
            passed=True,
        )
        for i in range(40)
    ]
    return RunResult(
        task_id=f"BF-{idx:03d}",
        tool="test-tool",
        run_id="concurrency_test_run1",
        timestamp="2026-01-01T00:00:00+00:00",
        outcome=RunOutcome(
            success=True,
            partial_credit_score=400,
            partial_credit_max=400,
            breakdown=breakdown,
        ),
        metrics=RunMetrics(wall_clock_seconds=1.0),
        cost=RunCost(input_tokens=1000, output_tokens=500),
        quality=RunQuality(),
        environment=RunEnvironment(os="test", hardware="test"),
    )


@pytest.mark.asyncio
async def test_jsonl_append_serializes_under_concurrency(tmp_path: Path) -> None:
    """100 concurrent writes -> 100 valid JSONL lines, no interleaving."""
    recorder = ResultRecorder(results_dir=tmp_path)

    async def write_one(i: int) -> None:
        # ResultRecorder.save is sync; run in default executor to interleave.
        await asyncio.to_thread(recorder.save, _make_result(i))

    await asyncio.gather(*[write_one(i) for i in range(100)])

    jsonl_path = tmp_path / "concurrency_test.jsonl"
    assert jsonl_path.exists(), (
        f"Expected JSONL at {jsonl_path}, listing: {list(tmp_path.iterdir())}"
    )

    line_count = 0
    for line in jsonl_path.read_text().splitlines():
        if not line.strip():
            continue
        line_count += 1
        # Each line must be a complete, valid JSON object.
        rec = json.loads(line)
        assert "task_id" in rec
        assert "outcome" in rec
        assert rec["outcome"]["partial_credit_score"] == 400

    assert line_count == 100, f"Expected 100 valid JSONL records, got {line_count}"
