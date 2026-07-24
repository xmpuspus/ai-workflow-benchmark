"""Tests for the warmup command."""

import re
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from awb.cli import cli
from awb.commands.warmup import _template_key


def _tasks_total(output: str) -> int:
    match = re.search(r"(\d+) tasks total", output)
    assert match, f"'tasks total' not found in output: {output!r}"
    return int(match.group(1))


def test_template_key_consistent():
    key = _template_key("https://github.com/org/repo", "abc1234", ["pip install -e ."])
    assert key == _template_key("https://github.com/org/repo", "abc1234", ["pip install -e ."])


def test_template_key_length():
    key = _template_key("https://github.com/org/repo", "abc1234", [])
    assert len(key) == 16


def test_template_key_differs_by_url():
    a = _template_key("https://github.com/org/repo-a", "abc1234", [])
    b = _template_key("https://github.com/org/repo-b", "abc1234", [])
    assert a != b


def test_template_key_differs_by_commit():
    a = _template_key("https://github.com/org/repo", "abc1234", [])
    b = _template_key("https://github.com/org/repo", "def5678", [])
    assert a != b


def test_template_key_setup_commands_order_independent():
    # sorted() makes setup_commands order-independent
    a = _template_key("u", "c", ["cmd1", "cmd2"])
    b = _template_key("u", "c", ["cmd2", "cmd1"])
    assert a == b


def test_warmup_dry_run(sample_task):
    runner = CliRunner()
    with patch("awb.core.task_loader.load_all_tasks", return_value=[sample_task]):
        result = runner.invoke(cli, ["warmup", "--dry-run"])
    assert result.exit_code == 0
    assert "templates to build" in result.output


def test_warmup_dry_run_deduplicates(sample_task):
    # Two tasks sharing the same repo/commit/setup should collapse to 1 template
    task2 = MagicMock()
    task2.id = "BF-002"
    task2.repo.url = sample_task.repo.url
    task2.repo.commit = sample_task.repo.commit
    task2.repo.setup_commands = sample_task.repo.setup_commands

    runner = CliRunner()
    with patch("awb.core.task_loader.load_all_tasks", return_value=[sample_task, task2]):
        result = runner.invoke(cli, ["warmup", "--dry-run"])
    assert result.exit_code == 0
    assert "1 templates to build" in result.output


def test_warmup_clear():
    runner = CliRunner()
    mock_mgr = MagicMock()
    with patch("awb.core.repo_manager.RepoManager", return_value=mock_mgr):
        result = runner.invoke(cli, ["warmup", "--clear"])
    assert result.exit_code == 0
    assert "cleared" in result.output
    mock_mgr.clear_templates.assert_called_once()


def test_warmup_fast_check_prints_notice():
    result = CliRunner().invoke(cli, ["warmup", "--fast-check", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Fast-check mode" in result.output


def test_warmup_fast_check_warms_only_eight_tasks():
    result = CliRunner().invoke(cli, ["warmup", "--fast-check", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert _tasks_total(result.output) <= 8


def test_warmup_fast_check_warms_fewer_tasks_than_full_run():
    runner = CliRunner()
    full = runner.invoke(cli, ["warmup", "--dry-run"])
    fast = runner.invoke(cli, ["warmup", "--fast-check", "--dry-run"])
    assert full.exit_code == 0, full.output
    assert fast.exit_code == 0, fast.output
    assert _tasks_total(fast.output) < _tasks_total(full.output)
