"""Integration tests for CLI commands."""
import json
import tempfile
from pathlib import Path

import yaml


def test_partial_credit_sum_validation():
    """validate_task_yaml rejects tasks where partial_credit doesn't sum to 100."""
    from awb.core.task_loader import validate_task_yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        bad_task = {
            "id": "BF-099",
            "category": "bug-fix",
            "title": "Test task with bad partial credit that is long enough",
            "difficulty": "easy",
            "estimated_minutes": 10,
            "languages": ["python"],
            "repo": {"url": "https://github.com/test/test", "commit": "abc1234"},
            "issue": {"description": "Fix a bug in the application code"},
            "verification": {
                "test_commands": ["pytest"],
                "partial_credit": [
                    {"criterion": "A", "points": 60, "check": "true"},
                    {"criterion": "B", "points": 30, "check": "true"},
                ],
            },
            "constraints": {"max_iterations": 20, "timeout_seconds": 300},
        }
        task_file = Path(tmpdir) / "BF-099.yaml"
        with task_file.open("w") as f:
            yaml.dump(bad_task, f)

        errors = validate_task_yaml(task_file)
        assert any("100" in str(e) for e in errors), f"Expected sum-to-100 error, got: {errors}"


def test_migrate_results_adds_version():
    """migrate-results adds version field to v0.5.x results."""
    from click.testing import CliRunner

    from awb.cli import cli

    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = Path(tmpdir) / "old"
        new_dir = Path(tmpdir) / "new"
        old_dir.mkdir()

        result_data = {
            "task_id": "BF-001", "tool": "test",
            "outcome": {"success": True, "partial_credit_score": 100, "partial_credit_max": 100},
        }
        with (old_dir / "BF-001.json").open("w") as f:
            json.dump(result_data, f)

        runner = CliRunner()
        result = runner.invoke(cli, ["migrate-results", str(old_dir), "--output", str(new_dir)])
        assert result.exit_code == 0

        migrated = list(new_dir.rglob("*.json"))
        assert len(migrated) == 1
        with migrated[0].open() as f:
            data = json.load(f)
        assert data["version"] == "1.0"
        assert "_v05x_original" in data
