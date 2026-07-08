"""Tests for awb/analysis/cost.py and the cost CLI command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from awb.analysis.cost import build_cost_report
from awb.commands.cost_cmd import cost
from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
)


def _make_result(
    task_id,
    tool,
    success=True,
    cost_usd=1.0,
    input_tokens=1000,
    output_tokens=500,
    score=100,
    max_score=100,
):
    return RunResult(
        task_id=task_id,
        tool=tool,
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        outcome=RunOutcome(
            success=success, partial_credit_score=score, partial_credit_max=max_score
        ),
        metrics=RunMetrics(),
        cost=RunCost(
            input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=cost_usd
        ),
        quality=RunQuality(),
        environment=RunEnvironment(os="darwin", hardware="test"),
    )


def _write_result_file(dir_path, result: RunResult):
    fname = f"{result.task_id}_{result.tool}.json"
    data = {
        "task_id": result.task_id,
        "tool": result.tool,
        "run_id": result.run_id,
        "timestamp": result.timestamp,
        "outcome": {
            "success": result.outcome.success,
            "partial_credit_score": result.outcome.partial_credit_score,
            "partial_credit_max": result.outcome.partial_credit_max,
        },
        "cost": {
            "input_tokens": result.cost.input_tokens,
            "output_tokens": result.cost.output_tokens,
            "estimated_cost_usd": result.cost.estimated_cost_usd,
        },
    }
    (dir_path / fname).write_text(json.dumps(data))


class TestBuildCostReport:
    def test_cost_aggregation_math(self):
        results = [
            _make_result(
                "BF-001", "tool-a", success=True, cost_usd=1.0, input_tokens=1000, output_tokens=500
            ),
            _make_result(
                "CR-001",
                "tool-a",
                success=True,
                cost_usd=2.0,
                input_tokens=2000,
                output_tokens=1000,
            ),
            _make_result(
                "DB-001", "tool-a", success=False, cost_usd=0.5, input_tokens=500, output_tokens=100
            ),
        ]

        reports = build_cost_report(results)

        assert len(reports) == 1
        r = reports[0]
        assert r.tool == "tool-a"
        assert r.n_tasks == 3
        assert r.n_solved == 2
        assert r.total_cost_usd == 3.5
        assert r.cost_per_task == round(3.5 / 3, 4)
        # cost_per_solved is total spend (waste included) / n_solved: 3.5 / 2
        assert r.cost_per_solved == 1.75
        assert r.wasted_cost_usd == 0.5
        assert r.total_tokens == 5100
        # tokens_per_solved likewise uses total tokens across all tasks: 5100 / 2
        assert r.tokens_per_solved == 2550.0

    def test_cost_per_solved_none_when_zero_solved(self):
        results = [
            _make_result("BF-001", "tool-b", success=False, cost_usd=0.3),
            _make_result("CR-001", "tool-b", success=False, cost_usd=0.4),
        ]

        reports = build_cost_report(results)

        r = reports[0]
        assert r.n_solved == 0
        assert r.cost_per_solved is None
        assert r.tokens_per_solved is None
        assert r.wasted_cost_usd == round(0.7, 4)

    def test_grouped_by_tool(self):
        results = [
            _make_result("BF-001", "tool-a", success=True, cost_usd=1.0),
            _make_result("BF-001", "tool-b", success=True, cost_usd=5.0),
        ]

        reports = build_cost_report(results)

        tools = {r.tool for r in reports}
        assert tools == {"tool-a", "tool-b"}

    def test_sorted_cheapest_per_solved_first(self):
        results = [
            _make_result("BF-001", "expensive", success=True, cost_usd=10.0),
            _make_result("BF-001", "cheap", success=True, cost_usd=1.0),
        ]

        reports = build_cost_report(results)

        assert [r.tool for r in reports] == ["cheap", "expensive"]

    def test_none_cost_per_solved_sorts_last(self):
        results = [
            _make_result("BF-001", "all-failed", success=False, cost_usd=1.0),
            _make_result("BF-001", "solved", success=True, cost_usd=10.0),
        ]

        reports = build_cost_report(results)

        assert [r.tool for r in reports] == ["solved", "all-failed"]
        assert reports[-1].cost_per_solved is None

    def test_empty_results_returns_empty_list(self):
        assert build_cost_report([]) == []


class TestCostCommand:
    def test_text_format_shows_cheapest_tool(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_result_file(run_dir, _make_result("BF-001", "tool-a", success=True, cost_usd=1.0))
        _write_result_file(run_dir, _make_result("BF-001", "tool-b", success=True, cost_usd=5.0))

        runner = CliRunner()
        result = runner.invoke(cost, [str(run_dir)])
        assert result.exit_code == 0
        assert "tool-a" in result.output

    def test_json_format_emits_cost_reports(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_result_file(run_dir, _make_result("BF-001", "tool-a", success=True, cost_usd=1.0))

        runner = CliRunner()
        result = runner.invoke(cost, [str(run_dir), "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["tool"] == "tool-a"
        assert payload[0]["cost_per_solved"] == 1.0

    def test_all_failed_edge_shows_warning_not_crash(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_result_file(run_dir, _make_result("BF-001", "tool-a", success=False, cost_usd=1.0))

        runner = CliRunner()
        result = runner.invoke(cost, [str(run_dir)])
        assert result.exit_code == 0
        assert "no cost-per-solved" in result.output.lower()

    def test_empty_run_dir_exits_nonzero(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(cost, [str(run_dir)])
        assert result.exit_code == 1

    def test_multiple_run_dirs_combined(self, tmp_path):
        dir_1 = tmp_path / "run1"
        dir_1.mkdir()
        _write_result_file(dir_1, _make_result("BF-001", "tool-a", success=True, cost_usd=1.0))
        dir_2 = tmp_path / "run2"
        dir_2.mkdir()
        _write_result_file(dir_2, _make_result("CR-001", "tool-a", success=True, cost_usd=2.0))

        runner = CliRunner()
        result = runner.invoke(cost, [str(dir_1), str(dir_2), "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["n_tasks"] == 2


def test_build_cost_report_tolerates_none_cost_fields():
    # Deserialized JSON can carry present-but-null cost fields; the report
    # must treat them as zero, not crash on None arithmetic.
    results = [
        _make_result(
            "BF-001", "toolx", success=True, cost_usd=None, input_tokens=None, output_tokens=None
        ),
        _make_result("BF-002", "toolx", success=False, cost_usd=2.0),
    ]
    reports = build_cost_report(results)
    assert len(reports) == 1
    r = reports[0]
    assert r.total_cost_usd == 2.0
    assert r.wasted_cost_usd == 2.0
    assert r.cost_per_solved == 2.0
