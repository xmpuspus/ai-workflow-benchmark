"""Integration test: runner persists trace JSONL via on_event."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.results import ResultRecorder
from awb.core.runner import BenchmarkRunner


class _TraceFakeAdapter(ToolAdapter):
    name = "trace-fake"
    display_name = "Trace Fake"

    async def execute(
        self,
        prompt,
        workspace,
        max_turns=20,
        timeout_seconds=1800,
        on_event=None,
    ):
        if on_event is not None:
            on_event(
                {
                    "type": "assistant",
                    "message": {
                        "usage": {"input_tokens": 100, "output_tokens": 25},
                        "content": [],
                    },
                }
            )
            on_event({"type": "tool_use", "tool": "bash"})
        return ToolResult(success=True, raw_output="ok", stream_events=[])

    def check_available(self) -> bool:
        return True

    def get_config_hash(self) -> str:
        return "trace-fake-hash"

    def get_version(self) -> str:
        return "0.0.0"


@pytest.mark.asyncio
async def test_runner_writes_trace_jsonl_with_otel_attrs(
    tmp_path: Path, monkeypatch, sample_task
):
    # Point recorder at tmp_path so we can inspect emitted artifacts.
    monkeypatch.setenv("AWB_RESULTS_DIR", str(tmp_path / "runs"))

    # Build a runner without invoking _get_adapter (no adapter installed)
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.tool = "trace-fake"
    runner.tasks = [sample_task]
    runner.runs = 1
    runner.parallel = False
    runner.timeout_override = None
    runner.workflow = None
    runner.resume = False
    runner.concurrency = 1
    runner.adaptive = False
    runner.progressive = False
    runner._adapter = _TraceFakeAdapter()
    runner._run1_times = {}
    runner._run_id = "test_run_trace"
    runner._task_set_hash = "deadbeef" * 8
    runner._environment = sample_task.repo.__class__  # placeholder; replaced below

    # Use real environment + recorder + repo manager mocks
    from awb.core.config import RunEnvironment

    runner._environment = RunEnvironment(os="darwin", hardware="test")
    runner.recorder = ResultRecorder(results_dir=tmp_path / "runs")

    # Mock RepoManager.prepare/cleanup so we don't touch the network
    class _FakeRepoManager:
        async def prepare(self, task, run_id=None):
            ws = tmp_path / "ws" / task.id
            ws.mkdir(parents=True, exist_ok=True)
            return ws

        async def cleanup(self, ws):
            return None

        def get_modified_files(self, ws):
            return []

        def get_lines_changed(self, ws):
            return 0

    runner.repo_manager = _FakeRepoManager()

    result = await runner.run_single(sample_task, run_id="test_run_trace_run1", run_num=1)

    # The result must reference a trace path and pin the task_set_hash
    assert result.task_set_hash == "deadbeef" * 8
    assert result.trace_path == "BF-001_trace-fake.trace.jsonl"

    # The trace file must exist with two spans (LLM_REQUEST + TOOL_USE)
    trace_file = tmp_path / "runs" / "test_run_trace_run1" / result.trace_path
    assert trace_file.exists()
    spans = [json.loads(line) for line in trace_file.read_text().splitlines() if line]
    assert len(spans) == 2
    assert spans[0]["span_name"] == "gen_ai.client.operation"
    assert spans[0]["attributes"]["gen_ai.usage.input_tokens"] == 100
    assert spans[1]["span_name"] == "gen_ai.tool.use"
    assert spans[1]["attributes"]["gen_ai.tool.name"] == "bash"
