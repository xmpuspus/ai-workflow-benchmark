"""Saved-evidence report command contracts."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from awb.commands._shared import save_last_run
from awb.core.config import RunCost, RunEnvironment, RunMetrics, RunOutcome, RunQuality, RunResult
from awb.core.results import ResultRecorder


def _save_result(run_dir: Path, *, success: bool = True) -> None:
    ResultRecorder(run_dir.parent).save(
        RunResult(
            task_id="BF-001",
            tool="test-tool",
            run_id=run_dir.name,
            timestamp="2026-09-05T00:00:00+00:00",
            outcome=RunOutcome(
                success=success, partial_credit_score=100 if success else 20, partial_credit_max=100
            ),
            metrics=RunMetrics(wall_clock_seconds=12.5, iteration_count=2),
            cost=RunCost(estimated_cost_usd=0.42),
            quality=RunQuality(),
            environment=RunEnvironment(os="test", hardware="test"),
        )
    )


def test_report_json_reads_saved_result_without_adapter_calls(tmp_path, monkeypatch):
    from awb.cli import cli

    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "run-a"
    _save_result(run_dir)

    def fail_adapter_access(*_args, **_kwargs):
        raise AssertionError("report must not access adapters")

    monkeypatch.setattr("awb.adapters.registry.get_adapter", fail_adapter_access)
    result = CliRunner().invoke(cli, ["report", str(run_dir), "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "evidence_available"
    assert payload["counts"] == {"results": 1, "passed": 1, "failed": 0, "tasks": 1}
    assert payload["run_dir"] == str(run_dir)


def test_report_empty_directory_has_stable_json_contract(tmp_path):
    from awb.cli import cli

    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    result = CliRunner().invoke(cli, ["report", str(run_dir), "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "status": "no_evidence",
        "run_dir": str(run_dir),
        "counts": {"results": 0, "passed": 0, "failed": 0, "tasks": 0},
        "next_step": (
            "Run an explicit benchmark, then render this saved evidence with awb report last."
        ),
    }


def test_report_last_resolves_saved_run(tmp_path, monkeypatch):
    from awb.cli import cli

    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "run-last"
    _save_result(run_dir, success=False)
    save_last_run(run_dir)

    result = CliRunner().invoke(cli, ["report", "last", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["counts"]["failed"] == 1


def test_quickstart_skips_auth_unless_requested(monkeypatch):
    from awb.commands.validate import quickstart

    calls = []
    monkeypatch.setattr("awb.adapters.registry.list_adapters", lambda: [("test", "Test", True)])

    class Adapter:
        def supports_auth_check(self):
            return True

        def check_auth(self):
            calls.append(True)
            return True, ""

    monkeypatch.setattr("awb.adapters.registry.get_adapter", lambda _name: Adapter())
    monkeypatch.setattr("awb.core.task_loader.load_all_tasks", lambda: [])

    result = CliRunner().invoke(quickstart, [])
    assert result.exit_code == 0, result.output
    assert calls == []
    assert "Authentication skipped" in result.output

    result = CliRunner().invoke(quickstart, ["--check-auth"])
    assert result.exit_code == 0, result.output
    assert calls == [True]
