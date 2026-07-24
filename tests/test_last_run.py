"""Tests for --last-run plumbing: awb/commands/_shared.py's save_last_run /
resolve_run_dir, and the gap/cost/drift/trace commands falling back to the
saved run when the run_dir argument is omitted.

Every test chdir's into tmp_path (via monkeypatch) because save_last_run
writes the relative path results/.last_run - without isolation these tests
would read/write the real repo's results/ directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from awb.commands._shared import resolve_run_dir, save_last_run
from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
)


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _write_result(run_dir: Path, task_id: str, score: float = 80, tool: str = "claude-code-custom"):
    run_dir.mkdir(parents=True, exist_ok=True)
    result = RunResult(
        task_id=task_id,
        tool=tool,
        run_id=run_dir.name,
        timestamp="2026-01-01T00:00:00Z",
        outcome=RunOutcome(success=True, partial_credit_score=score, partial_credit_max=100),
        metrics=RunMetrics(),
        cost=RunCost(),
        quality=RunQuality(),
        environment=RunEnvironment(os="test", hardware="test"),
    )
    (run_dir / f"{task_id}_{tool}.json").write_text(json.dumps(result.to_dict()))


class TestSaveAndResolve:
    def test_resolve_returns_none_when_nothing_saved(self):
        assert resolve_run_dir(None) is None

    def test_resolve_returns_none_for_last_when_nothing_saved(self):
        assert resolve_run_dir("last") is None

    def test_save_then_resolve_none_returns_saved_path(self, tmp_path):
        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        save_last_run(run_dir)
        assert resolve_run_dir(None) == run_dir

    def test_save_then_resolve_last_literal_returns_saved_path(self, tmp_path):
        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        save_last_run(run_dir)
        assert resolve_run_dir("last") == run_dir

    def test_explicit_arg_wins_over_saved_path(self, tmp_path):
        saved = tmp_path / "results" / "runs" / "saved_run1"
        explicit = tmp_path / "results" / "runs" / "explicit_run1"
        save_last_run(saved)
        assert resolve_run_dir(str(explicit)) == explicit

    def test_pointer_file_lives_at_results_last_run(self, tmp_path):
        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        save_last_run(run_dir)
        pointer = tmp_path / "results" / ".last_run"
        assert pointer.exists()
        assert pointer.read_text().strip() == str(run_dir)

    def test_second_save_overwrites_first(self, tmp_path):
        first = tmp_path / "results" / "runs" / "run_a"
        second = tmp_path / "results" / "runs" / "run_b"
        save_last_run(first)
        save_last_run(second)
        assert resolve_run_dir(None) == second


class TestGapLastRun:
    def test_gap_falls_back_to_last_run_and_prints_note(self, tmp_path):
        from awb.commands.analyze import gap

        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        _write_result(run_dir, "BF-001")
        save_last_run(run_dir)

        result = CliRunner().invoke(gap, [])
        assert result.exit_code == 0, result.output
        assert "using last run" in result.output
        # Rich wraps long tmp_path lines at console width and the wrap can
        # fall inside the run dir name itself (it did on CI), so collapse
        # newlines before matching.
        assert run_dir.name in result.output.replace("\n", "")

    def test_gap_errors_cleanly_when_no_last_run_saved(self):
        from awb.commands.analyze import gap

        result = CliRunner().invoke(gap, [])
        assert result.exit_code == 2
        assert "no run" in result.output.lower() or "last" in result.output.lower()

    def test_gap_explicit_run_dir_does_not_print_note(self, tmp_path):
        from awb.commands.analyze import gap

        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        _write_result(run_dir, "BF-001")

        result = CliRunner().invoke(gap, [str(run_dir)])
        assert result.exit_code == 0, result.output
        assert "using last run" not in result.output

    def test_gap_explicit_nonexistent_run_dir_exits_two(self, tmp_path):
        """An explicit but nonexistent path is a tool/environment failure
        (exit 2), not 'ran fine and found nothing' (exit 1) - matches the
        contract in _shared.py's module docstring."""
        from awb.commands.analyze import gap

        missing = tmp_path / "does-not-exist"
        result = CliRunner().invoke(gap, [str(missing)])
        assert result.exit_code == 2, result.output

    def test_gap_json_format_stays_parseable_when_falling_back(self, tmp_path):
        """The last-run note is text-mode only - --format json stdout must
        stay a single parseable document (same rule drift already follows)."""
        from awb.commands.analyze import gap

        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        _write_result(run_dir, "BF-001")
        save_last_run(run_dir)

        result = CliRunner().invoke(gap, ["--format", "json"])
        assert result.exit_code == 0, result.output
        json.loads(result.output)


class TestCostLastRun:
    def test_cost_falls_back_to_last_run(self, tmp_path):
        from awb.commands.cost_cmd import cost

        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        _write_result(run_dir, "BF-001")
        save_last_run(run_dir)

        result = CliRunner().invoke(cost, [])
        assert result.exit_code == 0, result.output
        assert "using last run" in result.output

    def test_cost_errors_cleanly_when_no_last_run_saved(self):
        from awb.commands.cost_cmd import cost

        result = CliRunner().invoke(cost, [])
        assert result.exit_code == 2

    def test_cost_accepts_last_literal(self, tmp_path):
        """gap/drift/trace grade all document the 'last' literal; cost's own
        docstring only promised the omitted-argument case."""
        from awb.commands.cost_cmd import cost

        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        _write_result(run_dir, "BF-001")
        save_last_run(run_dir)

        result = CliRunner().invoke(cost, ["last"])
        assert result.exit_code == 0, result.output
        assert "using last run" in result.output

    def test_cost_explicit_nonexistent_run_dir_exits_two(self, tmp_path):
        from awb.commands.cost_cmd import cost

        missing = tmp_path / "does-not-exist"
        result = CliRunner().invoke(cost, [str(missing)])
        assert result.exit_code == 2, result.output

    def test_cost_json_format_stays_parseable_when_falling_back(self, tmp_path):
        from awb.commands.cost_cmd import cost

        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        _write_result(run_dir, "BF-001")
        save_last_run(run_dir)

        result = CliRunner().invoke(cost, ["--format", "json"])
        assert result.exit_code == 0, result.output
        json.loads(result.output)


class TestDriftLastRun:
    def test_drift_falls_back_to_last_run_for_run_dir(self, tmp_path):
        from awb.commands.drift_cmd import drift

        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        _write_result(run_dir, "BF-001", score=80)
        save_last_run(run_dir)

        baseline_dir = tmp_path / "baseline_run"
        _write_result(baseline_dir, "BF-001", score=80)

        result = CliRunner().invoke(drift, ["--baseline", str(baseline_dir)])
        assert result.exit_code == 0, result.output
        assert "using last run" in result.output

    def test_drift_errors_cleanly_when_no_last_run_saved(self, tmp_path):
        from awb.commands.drift_cmd import drift

        baseline_dir = tmp_path / "baseline_run"
        _write_result(baseline_dir, "BF-001", score=80)

        result = CliRunner().invoke(drift, ["--baseline", str(baseline_dir)])
        assert result.exit_code == 2

    def test_drift_explicit_nonexistent_run_dir_exits_two(self, tmp_path):
        """Before v1.6, click.Path(exists=True) caught this at argument
        parsing; loosening it to support --last-run must not regress an
        explicit typo'd path into an uncaught FileNotFoundError."""
        from awb.commands.drift_cmd import drift

        baseline_dir = tmp_path / "baseline_run"
        _write_result(baseline_dir, "BF-001", score=80)
        missing = tmp_path / "does-not-exist"

        result = CliRunner().invoke(drift, [str(missing), "--baseline", str(baseline_dir)])
        assert result.exception is None or isinstance(result.exception, SystemExit), result.output
        assert result.exit_code == 2, result.output


class TestTraceLastRun:
    def test_trace_grade_falls_back_to_last_run(self, tmp_path):
        from awb.commands.trace_cmd import trace

        run_dir = tmp_path / "results" / "runs" / "2026-01-01_run1"
        run_dir.mkdir(parents=True)
        save_last_run(run_dir)

        result = CliRunner().invoke(trace, ["grade"])
        assert result.exit_code == 0, result.output
        assert "using last run" in result.output

    def test_trace_grade_errors_cleanly_when_no_last_run_saved(self):
        from awb.commands.trace_cmd import trace

        result = CliRunner().invoke(trace, ["grade"])
        assert result.exit_code == 2

    def test_trace_grade_explicit_nonexistent_run_dir_exits_two(self, tmp_path):
        """Before this fix, a nonexistent explicit path silently exited 0
        ('No .trace.jsonl files found'), indistinguishable from a clean run
        with nothing to grade."""
        from awb.commands.trace_cmd import trace

        missing = tmp_path / "does-not-exist"
        result = CliRunner().invoke(trace, ["grade", str(missing)])
        assert result.exit_code == 2, result.output
