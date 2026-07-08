"""Tests for `awb task from-pr` and the `awb run --tasks-dir` option. All gh calls are mocked."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from awb.commands.run import run as run_cmd
from awb.commands.task_cmd import _next_task_id, task
from awb.core.task_loader import load_all_tasks

MERGE_SHA = "1234567890abcdef1234567890abcdef1234567"
PREMERGE_SHA = "abcdef1234567890abcdef1234567890abcdef1"


def _fake_gh_run(responses: dict[str, object]):
    def _run(cmd, capture_output=True, text=True, timeout=30.0):
        assert cmd[0] == "gh"
        assert cmd[1] == "api"
        path = cmd[2]
        if path not in responses:
            raise AssertionError(f"No fake gh response registered for: {path}")
        return SimpleNamespace(returncode=0, stdout=json.dumps(responses[path]), stderr="")

    return _run


@pytest.fixture
def pr_responses():
    return {
        "repos/acme/widgets/pulls/42": {
            "number": 42,
            "title": "Add rate limiting to the checkout API",
            "body": "Adds a token bucket rate limiter.",
            "merged": True,
            "merge_commit_sha": MERGE_SHA,
            "html_url": "https://github.com/acme/widgets/pull/42",
        },
        f"repos/acme/widgets/commits/{MERGE_SHA}": {
            "sha": MERGE_SHA,
            "parents": [{"sha": PREMERGE_SHA}],
        },
        "repos/acme/widgets/pulls/42/files?per_page=100": [
            {"filename": "src/ratelimit/bucket.py"},
            {"filename": "tests/test_bucket.py"},
        ],
    }


@pytest.fixture
def valid_task_dict():
    return {
        "id": "BF-099",
        "category": "bug-fix",
        "title": "Fix a test bug in the application code",
        "difficulty": "easy",
        "estimated_minutes": 10,
        "languages": ["python"],
        "tags": ["test"],
        "repo": {
            "url": "https://github.com/test/repo",
            "commit": "abc1234",
            "setup_commands": ["pip install -e ."],
        },
        "issue": {
            "description": "Fix the bug in module.py",
            "files_to_examine": ["module.py"],
        },
        "verification": {
            "test_commands": ["pytest tests/"],
            "lint_commands": [],
            "security_commands": [],
            "partial_credit": [
                {"criterion": "Fix applied", "points": 100, "check": "true"},
            ],
        },
        "constraints": {
            "max_iterations": 10,
            "timeout_seconds": 600,
        },
    }


class TestNextTaskId:
    def test_first_id_when_dir_empty(self, tmp_path):
        assert _next_task_id("feature-addition", [tmp_path]) == "FA-001"

    def test_skips_used_ids(self, tmp_path):
        (tmp_path / "FA-001.yaml").write_text("id: FA-001")
        (tmp_path / "FA-002.yaml").write_text("id: FA-002")
        assert _next_task_id("feature-addition", [tmp_path]) == "FA-003"

    def test_scans_multiple_dirs(self, tmp_path):
        out_dir = tmp_path / "out"
        pkg_dir = tmp_path / "pkg"
        out_dir.mkdir()
        pkg_dir.mkdir()
        (out_dir / "BF-001.yaml").write_text("id: BF-001")
        (pkg_dir / "BF-002.yaml").write_text("id: BF-002")
        assert _next_task_id("bug-fix", [out_dir, pkg_dir]) == "BF-003"

    def test_ignores_missing_dir(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        assert _next_task_id("debugging", [missing]) == "DB-001"


class TestFromPrCommand:
    def test_dry_run_writes_nothing(self, monkeypatch, tmp_path, pr_responses):
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(pr_responses))
        out_dir = tmp_path / "tasks"
        runner = CliRunner()
        result = runner.invoke(
            task,
            [
                "from-pr",
                "https://github.com/acme/widgets/pull/42",
                "--out",
                str(out_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert not out_dir.exists()
        assert "id:" not in "".join(
            p.name for p in tmp_path.glob("**/*.yaml")
        )  # no files written anywhere

    def test_writes_valid_task_yaml(self, monkeypatch, tmp_path, pr_responses):
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(pr_responses))
        out_dir = tmp_path / "tasks"
        runner = CliRunner()
        result = runner.invoke(
            task,
            [
                "from-pr",
                "https://github.com/acme/widgets/pull/42",
                "--out",
                str(out_dir),
                "--id",
                "FA-777",
            ],
        )
        assert result.exit_code == 0, result.output
        written = out_dir / "FA-777.yaml"
        assert written.exists()
        data = yaml.safe_load(written.read_text())
        assert data["id"] == "FA-777"
        assert data["repo"]["commit"] == PREMERGE_SHA
        assert data["label"] == "real_pr"

    def test_id_auto_increments_against_out_dir(self, monkeypatch, tmp_path, pr_responses):
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(pr_responses))
        # Isolate from the real packaged awb/tasks/ inventory so the next-free-id
        # math only reflects what this test seeds in out_dir.
        monkeypatch.setattr("awb.core.config.TASKS_DIR", tmp_path / "pkg_tasks_empty")
        out_dir = tmp_path / "tasks"
        out_dir.mkdir()
        (out_dir / "FA-001.yaml").write_text("id: FA-001")

        runner = CliRunner()
        result = runner.invoke(
            task,
            ["from-pr", "https://github.com/acme/widgets/pull/42", "--out", str(out_dir)],
        )
        assert result.exit_code == 0, result.output
        assert (out_dir / "FA-002.yaml").exists()

    def test_unmerged_pr_fails_loudly(self, monkeypatch, tmp_path):
        responses = {"repos/acme/widgets/pulls/42": {"number": 42, "title": "WIP", "merged": False}}
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(responses))
        runner = CliRunner()
        result = runner.invoke(
            task,
            [
                "from-pr",
                "https://github.com/acme/widgets/pull/42",
                "--out",
                str(tmp_path / "tasks"),
            ],
        )
        assert result.exit_code != 0
        assert "only merged PRs" in result.output

    def test_bad_pr_url_fails_loudly(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(task, ["from-pr", "not-a-url", "--out", str(tmp_path / "tasks")])
        assert result.exit_code != 0

    def test_invalid_id_option_rejected(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            task,
            [
                "from-pr",
                "https://github.com/acme/widgets/pull/42",
                "--out",
                str(tmp_path / "tasks"),
                "--id",
                "lowercase-1",
            ],
        )
        assert result.exit_code != 0


class TestRunTasksDir:
    def test_run_dry_run_loads_from_custom_tasks_dir(self, tmp_path, valid_task_dict):
        tasks_dir = tmp_path / "private_tasks"
        tasks_dir.mkdir()
        valid_task_dict["id"] = "BF-999"
        (tasks_dir / "BF-999.yaml").write_text(yaml.dump(valid_task_dict))

        fake_adapter = MagicMock()
        fake_adapter.check_available.return_value = True
        fake_adapter.supports_auth_check.return_value = False

        runner = CliRunner()
        with patch("awb.adapters.registry.get_adapter", return_value=fake_adapter):
            result = runner.invoke(
                run_cmd,
                ["claude-code-vanilla", "--tasks-dir", str(tasks_dir), "--dry-run", "-y"],
            )
        assert result.exit_code == 0, result.output
        assert "BF-999" in result.output

    def test_load_all_tasks_tasks_dir_isolated_from_packaged_tasks(self, tmp_path, valid_task_dict):
        tasks_dir = tmp_path / "private_tasks"
        tasks_dir.mkdir()
        valid_task_dict["id"] = "BF-998"
        (tasks_dir / "BF-998.yaml").write_text(yaml.dump(valid_task_dict))

        tasks = load_all_tasks(tasks_dir=tasks_dir)
        assert [t.id for t in tasks] == ["BF-998"]


class TestFromPrGuards:
    PR_URL = "https://github.com/acme/widgets/pull/42"

    def test_validation_failure_exits_one(self, monkeypatch, tmp_path, pr_responses):
        monkeypatch.setattr("subprocess.run", _fake_gh_run(pr_responses))
        monkeypatch.setattr(
            "awb.core.task_loader.validate_task_yaml",
            lambda path: ["points do not sum [/x] to 100"],
        )
        runner = CliRunner()
        result = runner.invoke(task, ["from-pr", self.PR_URL, "--out", str(tmp_path / "tasks")])
        assert result.exit_code == 1
        assert "failed validation" in result.output

    def test_dry_run_survives_rich_markup_in_pr_title(self, monkeypatch, tmp_path, pr_responses):
        # PR-author-controlled text must never be parsed as Rich markup.
        pr_responses["repos/acme/widgets/pulls/42"]["title"] = "Fix bug[/x] in [red]parser"
        monkeypatch.setattr("subprocess.run", _fake_gh_run(pr_responses))
        runner = CliRunner()
        result = runner.invoke(
            task, ["from-pr", self.PR_URL, "--out", str(tmp_path / "tasks"), "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "Fix bug[/x]" in result.output

    def test_resume_with_tasks_dir_is_refused(self, tmp_path):
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            run_cmd, ["claude-code-custom", "--tasks-dir", str(tasks_dir), "--resume"]
        )
        assert result.exit_code == 1
        assert "--resume" in result.output
