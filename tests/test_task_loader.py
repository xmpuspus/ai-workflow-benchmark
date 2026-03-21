"""Tests for task YAML loading and validation."""
import tempfile
from pathlib import Path

import pytest
import yaml

from awb.core.config import TaskDefinition
from awb.core.task_loader import load_all_tasks, load_task, validate_task_yaml


def _write_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f)


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


class TestValidateTaskYaml:
    def test_valid_task_passes(self, valid_task_dict):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(valid_task_dict, f)
            path = Path(f.name)
        errors = validate_task_yaml(path)
        assert errors == []
        path.unlink()

    def test_missing_required_field(self, valid_task_dict):
        del valid_task_dict["id"]
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(valid_task_dict, f)
            path = Path(f.name)
        errors = validate_task_yaml(path)
        assert len(errors) > 0
        path.unlink()

    def test_invalid_difficulty(self, valid_task_dict):
        valid_task_dict["difficulty"] = "impossible"
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(valid_task_dict, f)
            path = Path(f.name)
        errors = validate_task_yaml(path)
        assert len(errors) > 0
        path.unlink()

    def test_invalid_id_format(self, valid_task_dict):
        valid_task_dict["id"] = "invalid"
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(valid_task_dict, f)
            path = Path(f.name)
        errors = validate_task_yaml(path)
        assert len(errors) > 0
        path.unlink()


class TestLoadTask:
    def test_loads_valid_task(self, valid_task_dict):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(valid_task_dict, f)
            path = Path(f.name)
        task = load_task(path)
        assert isinstance(task, TaskDefinition)
        assert task.id == "BF-099"
        assert task.category == "bug-fix"
        assert task.difficulty == "easy"
        assert task.languages == ["python"]
        path.unlink()


class TestLoadAllTasks:
    def test_loads_from_tasks_dir(self):
        """Smoke test - loads whatever tasks exist in the tasks/ directory."""
        tasks = load_all_tasks()
        # May be empty if no valid tasks exist yet, but shouldn't error
        assert isinstance(tasks, list)
