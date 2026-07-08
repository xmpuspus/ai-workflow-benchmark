"""Tests for `awb ab` - paired config A/B testing (awb/scoring/ab.py, awb/commands/ab_cmd.py).

FakeAdapter follows the pattern in tests/test_runner_parallelism.py's
_FakeAdapter and tests/conftest.py's FakeAdapter - no real Claude Code calls,
no network.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
)
from awb.scoring.ab import ABReport, ABTaskDelta, build_ab_report


def _result(task_id: str, tool: str, score: float, max_score: float = 100) -> RunResult:
    return RunResult(
        task_id=task_id,
        tool=tool,
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        outcome=RunOutcome(
            success=score == max_score, partial_credit_score=score, partial_credit_max=max_score
        ),
        metrics=RunMetrics(),
        cost=RunCost(),
        quality=RunQuality(),
        environment=RunEnvironment(os="test", hardware="test"),
    )


class TestBuildABReport:
    def test_pairs_by_task_id_and_computes_delta(self):
        # Deterministic: B beats A on every task by a shrinking margin.
        results_a = [
            _result("T1", "tool", 50),
            _result("T2", "tool", 50),
            _result("T3", "tool", 50),
            _result("T4", "tool", 50),
            _result("T5", "tool", 50),
            _result("T6", "tool", 50),
        ]
        results_b = [
            _result("T1", "tool", 90),
            _result("T2", "tool", 80),
            _result("T3", "tool", 70),
            _result("T4", "tool", 60),
            _result("T5", "tool", 55),
            _result("T6", "tool", 52),
        ]

        report = build_ab_report(results_a, results_b, label_a="A-dir", label_b="B-dir")

        assert isinstance(report, ABReport)
        assert report.tool == "tool"
        assert report.n_tasks == 6
        assert report.mean_delta == pytest.approx(17.8)
        assert report.significant is True
        assert report.p_value is not None
        assert report.p_value < 0.05
        assert "B-dir" in report.message

    def test_per_task_deltas_are_computed_and_sorted_by_magnitude(self):
        results_a = [_result("T1", "tool", 50), _result("T2", "tool", 50)]
        results_b = [_result("T1", "tool", 60), _result("T2", "tool", 90)]

        report = build_ab_report(results_a, results_b, label_a="A-dir", label_b="B-dir")

        assert report.per_task[0] == ABTaskDelta(
            task_id="T2", score_a=50.0, score_b=90.0, delta=40.0
        )
        assert report.per_task[1] == ABTaskDelta(
            task_id="T1", score_a=50.0, score_b=60.0, delta=10.0
        )

    def test_unpaired_tasks_are_dropped(self):
        results_a = [
            _result("T1", "tool", 50),
            _result("T2", "tool", 50),
            _result("T3", "tool", 50),
        ]
        results_b = [
            _result("T2", "tool", 60),
            _result("T3", "tool", 60),
            _result("T4", "tool", 60),
        ]

        report = build_ab_report(results_a, results_b, label_a="A-dir", label_b="B-dir")

        paired_ids = {d.task_id for d in report.per_task}
        assert paired_ids == {"T2", "T3"}
        assert report.n_tasks == 2

    def test_no_shared_tasks_returns_empty_report(self):
        results_a = [_result("T1", "tool", 50)]
        results_b = [_result("T2", "tool", 50)]

        report = build_ab_report(results_a, results_b, label_a="A-dir", label_b="B-dir")

        assert report.n_tasks == 0
        assert report.per_task == []
        assert report.p_value is None
        assert report.significant is False
        assert "No shared tasks" in report.message

    def test_config_hashes_pass_through(self):
        results_a = [_result("T1", "tool", 50)]
        results_b = [_result("T1", "tool", 50)]

        report = build_ab_report(
            results_a,
            results_b,
            label_a="A-dir",
            label_b="B-dir",
            config_hash_a="hash-a",
            config_hash_b="hash-b",
        )

        assert report.config_hash_a == "hash-a"
        assert report.config_hash_b == "hash-b"

    def test_identical_scores_are_not_significant(self):
        results_a = [_result(f"T{i}", "tool", 70) for i in range(6)]
        results_b = [_result(f"T{i}", "tool", 70) for i in range(6)]

        report = build_ab_report(results_a, results_b, label_a="A-dir", label_b="B-dir")

        assert report.mean_delta == pytest.approx(0.0, abs=1e-9)
        assert report.significant is False


class _UnsupportedFakeAdapter(ToolAdapter):
    """Mirrors a config-dir-less adapter - does not opt into supports_config_dir."""

    name = "fake-unsupported"
    display_name = "Fake Unsupported"

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=1800, on_event=None):
        return ToolResult(success=True)

    def check_available(self) -> bool:
        return True

    def get_config_hash(self) -> str:
        return "h"


class TestABCommandErrors:
    def test_cli_errors_on_unsupported_adapter(self, monkeypatch, tmp_path):
        from awb.commands.ab_cmd import ab

        monkeypatch.setattr(
            "awb.adapters.registry.get_adapter", lambda name: _UnsupportedFakeAdapter()
        )
        config_a = tmp_path / "a"
        config_b = tmp_path / "b"
        config_a.mkdir()
        config_b.mkdir()

        cli_runner = CliRunner()
        result = cli_runner.invoke(
            ab,
            ["fake-unsupported", "--config-a", str(config_a), "--config-b", str(config_b)],
        )

        assert result.exit_code != 0
        combined = (result.output or "") + str(result.exception or "")
        assert "does not support" in combined

    def test_cli_errors_on_unknown_tool(self, monkeypatch, tmp_path):
        from awb.commands.ab_cmd import ab

        def _raise(name):
            raise ValueError(f"Unknown adapter '{name}'. Available: fake")

        monkeypatch.setattr("awb.adapters.registry.get_adapter", _raise)
        config_a = tmp_path / "a"
        config_b = tmp_path / "b"
        config_a.mkdir()
        config_b.mkdir()

        cli_runner = CliRunner()
        result = cli_runner.invoke(
            ab,
            ["nonexistent-tool", "--config-a", str(config_a), "--config-b", str(config_b)],
        )

        assert result.exit_code != 0


class _SupportedFakeAdapter(ToolAdapter):
    """Config-dir-aware fake - records the config_dir it was built with."""

    name = "fake-supported"
    display_name = "Fake Supported"
    supports_config_dir = True

    def __init__(self, config_dir=None):
        self.config_dir = config_dir

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=1800, on_event=None):
        return ToolResult(success=True)

    def check_available(self) -> bool:
        return True

    def get_config_hash(self) -> str:
        return f"hash:{self.config_dir}"


class TestABCommandHappyPath:
    def test_cli_wires_two_configs_into_report(self, monkeypatch, tmp_path, sample_task):
        """Full CLI wiring, with `_run_config` faked out so no BenchmarkRunner /
        RepoManager / subprocess ever runs - zero network, zero real tool calls.
        """
        from awb.commands import ab_cmd

        monkeypatch.setattr(
            "awb.adapters.registry.get_adapter", lambda name: _SupportedFakeAdapter()
        )
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks", lambda category=None: [sample_task]
        )

        seen_run_ids = []

        def _fake_run_config(tool, adapter, tasks, run_id, timeout, runs_dir):
            seen_run_ids.append(run_id)
            score = 90 if run_id.endswith("_ab_a") else 60
            return [_result(tasks[0].id, tool, score)]

        monkeypatch.setattr(ab_cmd, "_run_config", _fake_run_config)

        config_a = tmp_path / "a"
        config_b = tmp_path / "b"
        config_a.mkdir()
        config_b.mkdir()

        cli_runner = CliRunner()
        result = cli_runner.invoke(
            ab_cmd.ab,
            [
                "fake-supported",
                "--config-a",
                str(config_a),
                "--config-b",
                str(config_b),
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["n_tasks"] == 1
        # A single shared task is below compare_tools_paired's n>=5
        # significance floor, so mean_delta is forced to 0.0 even though the
        # per-task delta below is real - same convention as workflow_lift.py.
        assert data["mean_delta"] == pytest.approx(0.0, abs=1e-9)
        assert data["per_task"][0]["task_id"] == sample_task.id
        assert data["per_task"][0]["delta"] == pytest.approx(-30.0)
        assert len(seen_run_ids) == 2
        assert seen_run_ids[0].endswith("_ab_a")
        assert seen_run_ids[1].endswith("_ab_b")

    def test_cli_errors_when_no_tasks_match_task_filter(self, monkeypatch, tmp_path, sample_task):
        from awb.commands import ab_cmd

        monkeypatch.setattr(
            "awb.adapters.registry.get_adapter", lambda name: _SupportedFakeAdapter()
        )
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks", lambda category=None: [sample_task]
        )

        config_a = tmp_path / "a"
        config_b = tmp_path / "b"
        config_a.mkdir()
        config_b.mkdir()

        cli_runner = CliRunner()
        result = cli_runner.invoke(
            ab_cmd.ab,
            [
                "fake-supported",
                "--config-a",
                str(config_a),
                "--config-b",
                str(config_b),
                "--task",
                "NONEXISTENT-ID",
            ],
        )

        assert result.exit_code != 0


class _ConfigBBrokenAdapter(_SupportedFakeAdapter):
    """Available for config A but not for a config dir named 'bad'."""

    name = "fake-b-broken"

    def check_available(self) -> bool:
        return not str(self.config_dir).endswith("bad")


class TestABPreflight:
    def test_config_b_unavailable_fails_before_any_run(self, monkeypatch, tmp_path, sample_task):
        from awb.commands import ab_cmd

        monkeypatch.setattr(
            "awb.adapters.registry.get_adapter", lambda name: _ConfigBBrokenAdapter()
        )
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks", lambda category=None: [sample_task]
        )

        def _must_not_run(*args, **kwargs):
            raise AssertionError("config A ran despite config B being unavailable")

        monkeypatch.setattr(ab_cmd, "_run_config", _must_not_run)

        config_a = tmp_path / "a"
        config_b = tmp_path / "bad"
        config_a.mkdir()
        config_b.mkdir()

        cli_runner = CliRunner()
        result = cli_runner.invoke(
            ab_cmd.ab,
            ["fake-b-broken", "--config-a", str(config_a), "--config-b", str(config_b)],
        )
        assert result.exit_code == 1
        assert "config B" in result.output

    def test_small_sample_verdict_names_the_sign_test_floor(
        self, monkeypatch, tmp_path, sample_task
    ):
        import dataclasses as dc

        from awb.commands import ab_cmd

        tasks = [dc.replace(sample_task, id=f"BF-00{i}") for i in (1, 2, 3)]
        monkeypatch.setattr(
            "awb.adapters.registry.get_adapter", lambda name: _SupportedFakeAdapter()
        )
        monkeypatch.setattr("awb.core.task_loader.load_all_tasks", lambda category=None: tasks)

        def _fake_run_config(tool, adapter, task_list, run_id, timeout, runs_dir):
            score = 90 if run_id.endswith("_ab_a") else 60
            return [_result(t.id, tool, score) for t in task_list]

        monkeypatch.setattr(ab_cmd, "_run_config", _fake_run_config)

        config_a = tmp_path / "a"
        config_b = tmp_path / "b"
        config_a.mkdir()
        config_b.mkdir()

        cli_runner = CliRunner()
        result = cli_runner.invoke(
            ab_cmd.ab,
            ["fake-supported", "--config-a", str(config_a), "--config-b", str(config_b)],
        )
        assert result.exit_code == 0, result.output
        # Under 5 pairs the sign test cannot run; the verdict must say so
        # instead of claiming "no significant difference".
        assert "Need 5+" in result.output


class TestBWorseSignificant:
    def test_b_worse_names_a_as_winner_in_message(self):
        tasks = [f"BF-00{i}" for i in range(1, 7)]
        results_a = [_result(t, "toolx", 90) for t in tasks]
        results_b = [_result(t, "toolx", 50) for t in tasks]
        report = build_ab_report(results_a, results_b, "cfgA", "cfgB")
        assert report.mean_delta < 0
        assert report.significant is True
        # The winner/loser swap must name config A as the higher scorer.
        assert report.message.startswith("cfgA scores higher")

    def test_cli_verdict_says_config_b_hurts(self, monkeypatch, tmp_path, sample_task):
        import dataclasses as dc

        from awb.commands import ab_cmd

        tasks = [dc.replace(sample_task, id=f"BF-00{i}") for i in range(1, 7)]
        monkeypatch.setattr(
            "awb.adapters.registry.get_adapter", lambda name: _SupportedFakeAdapter()
        )
        monkeypatch.setattr("awb.core.task_loader.load_all_tasks", lambda category=None: tasks)

        def _fake_run_config(tool, adapter, task_list, run_id, timeout, runs_dir):
            score = 90 if run_id.endswith("_ab_a") else 50
            return [_result(t.id, tool, score) for t in task_list]

        monkeypatch.setattr(ab_cmd, "_run_config", _fake_run_config)
        config_a = tmp_path / "a"
        config_b = tmp_path / "b"
        config_a.mkdir()
        config_b.mkdir()
        result = CliRunner().invoke(
            ab_cmd.ab,
            ["fake-supported", "--config-a", str(config_a), "--config-b", str(config_b)],
        )
        assert result.exit_code == 0, result.output
        assert "config B hurts relative to config A" in result.output
