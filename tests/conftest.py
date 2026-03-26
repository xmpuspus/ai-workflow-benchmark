"""Shared test fixtures for AWB tests."""
import tempfile
from pathlib import Path

import pytest

from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.config import (
    PartialCreditCriterion,
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
    TaskConstraints,
    TaskDefinition,
    TaskRepo,
    TaskVerification,
)


@pytest.fixture
def sample_task():
    """A minimal valid TaskDefinition for testing."""
    return TaskDefinition(
        id="BF-001",
        category="bug-fix",
        title="Fix thread-unsafe session storage in Flask app",
        difficulty="medium",
        estimated_minutes=25,
        languages=["python"],
        tags=["concurrency", "flask"],
        repo=TaskRepo(
            url="https://github.com/pallets/flask",
            commit="4f1e4fa",
            setup_commands=["pip install -e ."],
        ),
        issue_description="Fix the race condition in session storage.",
        files_to_examine=["src/flask/sessions.py"],
        verification=TaskVerification(
            test_commands=["python3 -m pytest tests/test_sessions.py -v"],
            lint_commands=["ruff check src/flask/"],
            security_commands=[],
            partial_credit=[
                PartialCreditCriterion(
                    criterion="Adds locking",
                    points=50,
                    check="grep -q 'Lock' src/flask/sessions.py",
                ),
                PartialCreditCriterion(
                    criterion="Tests pass",
                    points=50,
                    check="python3 -m pytest tests/ -v",
                ),
            ],
        ),
        constraints=TaskConstraints(max_iterations=20, timeout_seconds=1800),
    )


@pytest.fixture
def tmp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory(prefix="awb-test-") as d:
        yield Path(d)


class FakeAdapter(ToolAdapter):
    """Test adapter that returns canned results."""

    name = "fake-tool"
    display_name = "Fake Tool"

    def __init__(self, success=True, output="done"):
        self._success = success
        self._output = output

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=1800):
        return ToolResult(
            success=self._success,
            raw_output=self._output,
            stream_events=[],
            exit_code=0 if self._success else 1,
            tool_version="fake-1.0",
            model="fake-model",
        )

    def check_available(self):
        return True

    def get_config_hash(self):
        return "fake-hash"


@pytest.fixture
def fake_adapter():
    return FakeAdapter()


@pytest.fixture
def sample_result():
    """A RunResult object for testing."""
    return RunResult(
        task_id="BF-001",
        tool="fake-tool",
        tool_version="1.0",
        model="fake-model",
        run_id="test-run",
        timestamp="2026-03-26T00:00:00Z",
        outcome=RunOutcome(
            success=True, partial_credit_score=80, partial_credit_max=100, breakdown=[]
        ),
        metrics=RunMetrics(
            wall_clock_seconds=120.0,
            iteration_count=5,
            human_interventions=0,
            tool_calls={"Read": 3},
            files_modified=2,
            lines_changed=30,
        ),
        cost=RunCost(input_tokens=50000, output_tokens=10000, estimated_cost_usd=0.42),
        quality=RunQuality(lint_delta=0, security_delta=0, test_regressions=0),
        environment=RunEnvironment(os="darwin", hardware="test"),
    )


@pytest.fixture
def sample_result_dict():
    """A valid result dict matching the result schema."""
    return {
        "task_id": "BF-001",
        "tool": "claude-code-vanilla",
        "tool_version": "1.0.42",
        "model": "claude-opus-4-6",
        "run_id": "2026-03-25_run1",
        "timestamp": "2026-03-25T14:30:00Z",
        "outcome": {
            "success": True,
            "partial_credit_score": 90,
            "partial_credit_max": 100,
            "breakdown": [
                {
                    "criterion": "Adds locking",
                    "points_earned": 50,
                    "points_possible": 50,
                    "passed": True,
                },
                {
                    "criterion": "Tests pass",
                    "points_earned": 40,
                    "points_possible": 50,
                    "passed": False,
                },
            ],
        },
        "metrics": {
            "wall_clock_seconds": 247.3,
            "iteration_count": 8,
            "human_interventions": 0,
            "tool_calls": {"Read": 5, "Edit": 3, "Bash": 12},
            "files_modified": 1,
            "lines_changed": 17,
        },
        "cost": {
            "input_tokens": 45230,
            "output_tokens": 12840,
            "estimated_cost_usd": 0.42,
        },
        "quality": {
            "lint_delta": 0,
            "security_delta": 0,
            "test_regressions": 0,
        },
        "environment": {
            "os": "darwin",
            "hardware": "Apple M3 Max 64GB",
        },
    }
