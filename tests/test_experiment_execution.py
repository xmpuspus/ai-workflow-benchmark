from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from awb.experiments.protocol import create_plan


def _task(path: Path, task_id: str) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "id": task_id,
                "category": "bug-fix",
                "title": "A controlled task",
                "difficulty": "easy",
                "estimated_minutes": 5,
                "languages": ["python"],
                "repo": {"url": "https://example.invalid/repo", "commit": "a" * 40},
                "issue": {"description": "Do work", "files_to_examine": []},
                "verification": {"partial_credit": []},
                "constraints": {"max_iterations": 1, "timeout_seconds": 60},
            },
            sort_keys=False,
        )
    )


def _configs(tmp_path: Path) -> tuple[Path, Path]:
    config_a, config_b = tmp_path / "config-a", tmp_path / "config-b"
    for path, instruction in ((config_a, "# baseline"), (config_b, "# candidate")):
        path.mkdir()
        (path / "settings.json").write_text('{"permissions":{"allow":["Read"]}}')
        (path / "hooks.json").write_text('{"hooks":{}}')
        (path / "CLAUDE.md").write_text(instruction)
    return config_a, config_b


def _plan(tmp_path: Path):
    from awb.experiments.execution import config_snapshot

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    _task(tasks_dir / "BF-001.yaml", "BF-001")
    config_a, config_b = _configs(tmp_path)
    task_hash = __import__("hashlib").sha256((tasks_dir / "BF-001.yaml").read_bytes()).hexdigest()
    a, b = config_snapshot(config_a), config_snapshot(config_b)
    plan = create_plan(
        {
            "tool": "claude-code-custom",
            "model": "claude-test-model",
            "config_a_hash": a["hash"],
            "config_b_hash": b["hash"],
            "safety_policy_hash_a": a["safety_policy_hash"],
            "safety_policy_hash_b": b["safety_policy_hash"],
            "task_hashes": {"BF-001": task_hash, "BF-001-HOLDOUT": "b" * 64},
            "development_tasks": ["BF-001"],
            "holdout_tasks": ["BF-001-HOLDOUT"],
            "repeats": 1,
            "seed": 7,
            "timeout_seconds": 120,
            "minimum_delta": 5,
            "state_policy": "fresh_process_per_attempt",
        }
    )
    # Keep the protocol's required holdout distinct without loading it in this development test.
    return plan, config_a, config_b, tasks_dir


def test_wrong_input_hash_rejected_before_attempt(monkeypatch, tmp_path):
    from awb.experiments.execution import execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    plan["spec"]["config_a_hash"] = "0" * 64
    plan = create_plan(plan["spec"])
    called = []
    monkeypatch.setattr(
        "awb.experiments.execution._execute_attempt", lambda *args, **kwargs: called.append(args)
    )

    with pytest.raises(ValueError, match="config A hash"):
        execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")
    assert called == []


def test_counterbalanced_attempts_are_receipted_and_resume_without_duplicates(
    monkeypatch, tmp_path
):
    from awb.experiments.execution import execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    calls = []

    def fake_attempt(**kwargs):
        calls.append((kwargs["arm"], kwargs["repeat_index"], kwargs["timeout_seconds"]))
        run_dir = kwargs["runs_dir"] / f"{kwargs['run_id']}_run1"
        run_dir.mkdir(parents=True)
        path = run_dir / f"{kwargs['task'].id}_claude-code-custom.json"
        path.write_text(
            json.dumps(
                {
                    "task_id": kwargs["task"].id,
                    "tool": "claude-code-custom",
                    "run_id": f"{kwargs['run_id']}_run1",
                    "model": "claude-test-model",
                    "outcome": {
                        "success": True,
                        "partial_credit_score": 100,
                        "partial_credit_max": 100,
                    },
                }
            )
        )
        return path

    monkeypatch.setattr("awb.experiments.execution._execute_attempt", fake_attempt)
    first = execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")
    assert [arm for arm, _, _ in calls] == [
        entry["arm"] for entry in plan["schedule"] if entry["split"] == "development"
    ]
    assert {timeout for _, _, timeout in calls} == {120}
    assert len(first["completed_attempts"]) == 2
    for row in first["completed_attempts"]:
        assert row["experiment_plan_hash"] == plan["plan_hash"]
        assert row["repeat_index"] == 1
        assert row["execution_status"] == "completed"
        assert row["effective_config_hash"] in {
            plan["spec"]["config_a_hash"],
            plan["spec"]["config_b_hash"],
        }

    second = execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")
    assert len(calls) == 2
    assert second["executed_attempts"] == []
    assert len(second["resumed_attempts"]) == 2


def test_started_marker_is_ambiguous_and_never_rerun(tmp_path):
    from awb.experiments.execution import _attempt_marker, execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    marker = _attempt_marker(tmp_path / "runs", plan["plan_hash"], "development", "BF-001", "a", 1)
    marker.parent.mkdir(parents=True)
    marker.write_text('{"status":"started"}')

    with pytest.raises(ValueError, match="(?i)ambiguous"):
        execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")


def test_config_snapshot_rejects_auth_or_state_files(tmp_path):
    from awb.experiments.execution import config_snapshot

    config = tmp_path / "config"
    config.mkdir()
    (config / "auth.json").write_text("do not read")
    with pytest.raises(ValueError, match="not permitted"):
        config_snapshot(config)


def test_model_is_explicitly_pinned_in_each_adapter_command(tmp_path):
    from awb.experiments.execution import _ModelPinnedClaudeAdapter

    adapter = _ModelPinnedClaudeAdapter(tmp_path, "claude-test-model")
    command = adapter._get_cmd("prompt", 3)
    assert command[-2:] == ["--model", "claude-test-model"]
