"""Tests for the P0 fast-check wiring bug in the tool-less `awb run` path.

`_run_both` (the "no tool given, run vanilla+custom" branch) used to take no
fast_check/progressive/use_uv/yes parameters, so `awb run --fast-check` with
no tool argument silently ran the full 100-task suite twice instead of the
intended 8 tasks x 1 run x 2 variants.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from awb.adapters.base import ToolAdapter, ToolResult
from awb.commands.run import run as run_cmd


class _RecordingRunner:
    """Fake BenchmarkRunner: records constructor kwargs, never executes anything."""

    instances: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _RecordingRunner.instances.append(kwargs)
        self._run_id = "test-run"
        self.recorder = SimpleNamespace(results_dir=Path(tempfile.mkdtemp()))

    async def run_all(self):
        return []


class _OkAdapter(ToolAdapter):
    name = "fake"
    display_name = "Fake"

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=1800, on_event=None):
        return ToolResult(success=True, raw_output="", stream_events=[])

    def check_available(self) -> bool:
        return True

    def get_config_hash(self) -> str:
        return "h"


class _AuthFailAdapter(_OkAdapter):
    def supports_auth_check(self) -> bool:
        return True

    def check_auth(self):
        return False, "not logged in"


def _reset():
    _RecordingRunner.instances = []


class TestRunBothFastCheckWiring:
    def test_fast_check_selects_eight_tasks_once_for_both_variants(self, monkeypatch):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())

        result = CliRunner().invoke(run_cmd, ["--fast-check", "-y"])

        assert result.exit_code == 0, result.output
        assert len(_RecordingRunner.instances) == 2
        for kwargs in _RecordingRunner.instances:
            assert len(kwargs["tasks"]) == 8
            assert kwargs["runs"] == 1
        assert "Fast-check mode" in result.output

    def test_fast_check_defaults_to_parallel_concurrency_4(self, monkeypatch):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())

        result = CliRunner().invoke(run_cmd, ["--fast-check", "-y"])

        assert result.exit_code == 0, result.output
        assert len(_RecordingRunner.instances) == 2
        for kwargs in _RecordingRunner.instances:
            assert kwargs["concurrency"] == 4
            assert kwargs["parallel"] is True

    def test_explicit_j_overrides_fast_check_default(self, monkeypatch):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())

        result = CliRunner().invoke(run_cmd, ["--fast-check", "-j", "2", "-y"])

        assert result.exit_code == 0, result.output
        for kwargs in _RecordingRunner.instances:
            assert kwargs["concurrency"] == 2

    def test_explicit_j_1_disables_forced_parallel(self, monkeypatch):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())

        result = CliRunner().invoke(run_cmd, ["--fast-check", "-j", "1", "-y"])

        assert result.exit_code == 0, result.output
        for kwargs in _RecordingRunner.instances:
            assert kwargs["concurrency"] == 1
            assert kwargs["parallel"] is False

    def test_fast_check_does_not_hit_confirmation_prompt(self, monkeypatch):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())

        # No -y: 8 tasks x 1 run must stay under the >10 confirmation
        # threshold so this never blocks waiting on stdin.
        result = CliRunner().invoke(run_cmd, ["--fast-check"], input="\n")

        assert result.exit_code == 0, result.output
        assert "About to run" not in result.output
        assert len(_RecordingRunner.instances) == 2

    def test_auth_preflight_runs_before_any_benchmark_runner_in_run_both(self, monkeypatch):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _AuthFailAdapter())

        result = CliRunner().invoke(run_cmd, ["--fast-check", "-y"])

        assert result.exit_code == 1
        assert "not logged in" in result.output
        assert _RecordingRunner.instances == []

    def test_progressive_and_use_uv_forwarded_in_run_both(self, monkeypatch):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())

        result = CliRunner().invoke(
            run_cmd, ["--fast-check", "--progressive", "--use-uv", "-y"]
        )

        assert result.exit_code == 0, result.output
        for kwargs in _RecordingRunner.instances:
            assert kwargs["progressive"] is True
            assert kwargs["use_uv"] is True

    def test_full_suite_confirmation_prompt_fires_and_aborts_without_yes(self, monkeypatch):
        # The other half of the P0 fix: the prompt must still fire (and a "no"
        # answer must still abort before any BenchmarkRunner is built) on the
        # tool-less full-suite path. This is the guard that prevents the
        # accidental ~$300 run; only testing the fast-check bypass would miss
        # a future inverted `not yes` regression here.
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())

        result = CliRunner().invoke(run_cmd, [], input="n\n")

        assert result.exit_code == 0, result.output
        assert "About to run" in result.output
        assert _RecordingRunner.instances == []

    def test_yes_skips_confirmation_in_run_both_for_full_suite(self, monkeypatch):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())

        result = CliRunner().invoke(run_cmd, ["-y"])

        assert result.exit_code == 0, result.output
        assert "About to run" not in result.output
        assert len(_RecordingRunner.instances) == 2
        # Full suite, no --fast-check: unchanged sequential default.
        for kwargs in _RecordingRunner.instances:
            assert kwargs["concurrency"] == 1
            assert kwargs["parallel"] is False


class TestNonFastCheckParallelDefaultUnchanged:
    def test_no_flags_stays_sequential_concurrency_1(self, monkeypatch, sample_task):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks",
            lambda tasks_dir=None, category=None: [sample_task],
        )

        result = CliRunner().invoke(run_cmd, ["fake", "-y"])

        assert result.exit_code == 0, result.output
        assert len(_RecordingRunner.instances) == 1
        assert _RecordingRunner.instances[0]["concurrency"] == 1
        assert _RecordingRunner.instances[0]["parallel"] is False

    def test_parallel_flag_alone_still_works_without_fast_check(self, monkeypatch, sample_task):
        _reset()
        monkeypatch.setattr("awb.core.runner.BenchmarkRunner", _RecordingRunner)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda name: _OkAdapter())
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks",
            lambda tasks_dir=None, category=None: [sample_task],
        )

        result = CliRunner().invoke(run_cmd, ["fake", "--parallel", "-y"])

        assert result.exit_code == 0, result.output
        assert _RecordingRunner.instances[0]["concurrency"] == 1
        assert _RecordingRunner.instances[0]["parallel"] is True
