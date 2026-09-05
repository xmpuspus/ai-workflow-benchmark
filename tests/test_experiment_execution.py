from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from awb.experiments.protocol import create_plan


@pytest.fixture(autouse=True)
def _skip_real_cli_preflight(monkeypatch, request):
    real_preflight_tests = {
        "test_runtime_preflight_rejects_missing_allowed_environment",
        "test_runtime_preflight_rejects_missing_cli",
    }
    if request.node.name not in real_preflight_tests:
        monkeypatch.setattr("awb.experiments.execution._preflight_runtime", lambda *args: None)


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


def test_nested_execution_receipt_is_reusable(monkeypatch, tmp_path):
    from awb.experiments.execution import execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    calls = []

    def attempt(**kwargs):
        calls.append(kwargs["arm"])
        directory = kwargs["runs_dir"] / kwargs["run_id"]
        directory.mkdir(parents=True)
        path = directory / "BF-001_claude-code-custom.json"
        path.write_text(
            json.dumps(
                {
                    "task_id": "BF-001",
                    "model": "claude-test-model",
                    "execution": {"status": "completed", "stage": "complete"},
                    "execution_mode": "host",
                    "outcome": {
                        "success": True,
                        "partial_credit_score": 100,
                        "partial_credit_max": 100,
                    },
                }
            )
        )
        return path

    monkeypatch.setattr("awb.experiments.execution._execute_attempt", attempt)
    first = execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")
    assert first["status"] == "completed"
    assert first["completed_attempts"][0]["execution_mode"] == "host"
    second = execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")
    assert len(second["resumed_attempts"]) == 2
    assert len(calls) == 2


def test_experiment_receipts_survive_result_serialization():
    from awb.core.config import (
        RunCost,
        RunEnvironment,
        RunMetrics,
        RunOutcome,
        RunQuality,
        RunResult,
    )
    from awb.core.results import _dict_to_result

    result = RunResult(
        task_id="BF-001",
        tool="test",
        run_id="r",
        timestamp="now",
        outcome=RunOutcome(False, 0, 100),
        metrics=RunMetrics(),
        cost=RunCost(),
        quality=RunQuality(),
        environment=RunEnvironment(),
        experiment_plan_hash="plan",
        repeat_index=2,
        experiment_arm="a",
    )
    loaded = _dict_to_result(result.to_dict())
    assert loaded.experiment_plan_hash == "plan"
    assert loaded.repeat_index == 2
    assert loaded.experiment_arm == "a"


def test_counterbalanced_attempts_are_receipted_and_resume_without_duplicates(
    monkeypatch, tmp_path
):
    from awb.experiments.execution import execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    calls = []

    def fake_attempt(**kwargs):
        calls.append(
            (kwargs["arm"], kwargs["repeat_index"], kwargs["timeout_seconds"], kwargs["config_dir"])
        )
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
                    "execution_status": "completed",
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
    assert [arm for arm, _, _, _ in calls] == [
        entry["arm"] for entry in plan["schedule"] if entry["split"] == "development"
    ]
    assert {timeout for _, _, timeout, _ in calls} == {120}
    assert len({path for _, _, _, path in calls}) == 2
    assert all(not path.exists() for _, _, _, path in calls)
    assert len(first["completed_attempts"]) == 2
    for row in first["completed_attempts"]:
        assert row["experiment_plan_hash"] == plan["plan_hash"]
        assert row["repeat_index"] == 1
        assert row["execution_status"] == "completed"
        assert row["requested_model"] == "claude-test-model"
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


def test_config_snapshot_rejects_root_symlink(tmp_path):
    from awb.experiments.execution import config_snapshot

    target = tmp_path / "target"
    target.mkdir()
    (target / "CLAUDE.md").write_text("instructions")
    link = tmp_path / "config-link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        config_snapshot(link)


def test_config_snapshot_rejects_nonregular_and_oversized_files(tmp_path):
    import os

    from awb.experiments.execution import config_snapshot

    config = tmp_path / "config"
    config.mkdir()
    fifo = config / "settings.json"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular file"):
        config_snapshot(config)
    fifo.unlink()
    oversized = config / "CLAUDE.md"
    with oversized.open("wb") as handle:
        handle.truncate(1024 * 1024 + 1)
    with pytest.raises(ValueError, match="size limit"):
        config_snapshot(config)


def test_holdout_requires_reviewed_controls_before_execution(monkeypatch, tmp_path):
    from awb.experiments.execution import execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    holdout = tasks_dir / "BF-001-HOLDOUT.yaml"
    _task(holdout, "BF-001-HOLDOUT")
    plan = create_plan(
        {
            **plan["spec"],
            "task_hashes": {
                **plan["spec"]["task_hashes"],
                "BF-001-HOLDOUT": __import__("hashlib").sha256(holdout.read_bytes()).hexdigest(),
            },
        }
    )
    called = []
    monkeypatch.setattr(
        "awb.experiments.execution._execute_attempt", lambda **kwargs: called.append(kwargs)
    )
    with pytest.raises(ValueError, match="control evidence"):
        execute_plan(plan, config_a, config_b, tasks_dir, "holdout", tmp_path / "runs")
    assert called == []


def test_config_snapshot_rejects_credential_environment_key_without_echoing_value(tmp_path):
    from awb.experiments.execution import config_snapshot

    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.json").write_text('{"env":{"API_TOKEN":"do-not-print-me"}}')
    with pytest.raises(ValueError) as error:
        config_snapshot(config)
    assert "API_TOKEN" not in str(error.value)
    assert "do-not-print-me" not in str(error.value)


def test_model_is_explicitly_pinned_in_each_adapter_command(tmp_path):
    from awb.experiments.execution import _ModelPinnedClaudeAdapter

    home, temp = tmp_path / "home", tmp_path / "tmp"
    home.mkdir()
    temp.mkdir()
    adapter = _ModelPinnedClaudeAdapter(tmp_path, "claude-test-model", home_dir=home, tmp_dir=temp)
    command = adapter._get_cmd("prompt", 3)
    assert command[-2:] == ["--model", "claude-test-model"]
    assert "--dangerously-skip-permissions" not in command


def test_experiment_adapter_forwards_only_named_environment(monkeypatch, tmp_path):
    from awb.experiments.execution import _ModelPinnedClaudeAdapter

    monkeypatch.setenv("UNRELATED_PRIVATE_TOKEN", "do-not-forward")
    monkeypatch.setenv("DECLARED_API_TOKEN", "forward")
    ambient_home, home, temp = "/private/home", tmp_path / "home", tmp_path / "tmp"
    monkeypatch.setenv("HOME", ambient_home)
    home.mkdir()
    temp.mkdir()
    for name in ("cache", "config", "state", "runtime"):
        (home / name).mkdir()
    adapter = _ModelPinnedClaudeAdapter(
        tmp_path,
        "claude-test-model",
        ("DECLARED_API_TOKEN",),
        home_dir=home,
        tmp_dir=temp,
    )
    environment = adapter._get_env()
    assert "UNRELATED_PRIVATE_TOKEN" not in environment
    assert environment["DECLARED_API_TOKEN"] == "forward"
    assert environment["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    assert environment["HOME"] == str(home)
    assert environment["HOME"] != ambient_home
    assert environment["TMPDIR"] == str(temp)
    assert set(environment) <= {
        "PATH",
        "HOME",
        "TMPDIR",
        "AWB_BENCHMARK",
        "CLAUDE_CONFIG_DIR",
        "DECLARED_API_TOKEN",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
    }


def test_isolated_attempt_uses_private_home_and_temp_state(monkeypatch, tmp_path):
    from awb.experiments.execution import _isolated_attempt, _ModelPinnedClaudeAdapter

    monkeypatch.setenv("HOME", "/ambient/home")
    monkeypatch.setenv("TMPDIR", "/ambient/tmp")
    snapshot = {"entries": [("CLAUDE.md", b"# instructions")]}
    with _isolated_attempt(snapshot, tmp_path) as (config_dir, home_dir, temp_dir):
        environment = _ModelPinnedClaudeAdapter(
            config_dir, "claude-test-model", home_dir=home_dir, tmp_dir=temp_dir
        )._get_env()
        assert environment["HOME"] == str(home_dir)
        assert environment["TMPDIR"] == str(temp_dir)
        assert environment["XDG_STATE_HOME"] == str(home_dir / "state")
        assert config_dir.joinpath("CLAUDE.md").read_text() == "# instructions"
        assert home_dir != Path("/ambient/home")
        assert temp_dir != Path("/ambient/tmp")
    assert not home_dir.exists()
    assert not temp_dir.exists()


def test_assess_rejects_malformed_imported_rows_and_unverified_holdout(tmp_path):
    from awb.experiments.protocol import assess, create_plan

    plan, _, _, _ = _plan(tmp_path)
    malformed = assess(plan, [[]], [{}], "development")
    assert malformed["decision"] == "inconclusive"
    assert any("not an object" in reason for reason in malformed["reasons"])

    holdout = assess(plan, [], [], "holdout")
    assert holdout["decision"] == "inconclusive"
    assert any("Unverified imported evidence" in reason for reason in holdout["reasons"])
    with pytest.raises(ValueError, match="JSON arrays"):
        assess(plan, {}, [], "development")
    with pytest.raises(ValueError, match="specification"):
        create_plan([])


def test_assess_rejects_nonfinite_scores_and_negative_costs(tmp_path):
    from awb.experiments.protocol import assess

    plan, _, _, _ = _plan(tmp_path)

    def receipt(arm, score, cost):
        return {
            "task_id": "BF-001",
            "model": "claude-test-model",
            "effective_config_hash": plan["spec"][f"config_{arm}_hash"],
            "task_definition_hash": plan["spec"]["task_hashes"]["BF-001"],
            "experiment_plan_hash": plan["plan_hash"],
            "experiment_split": "development",
            "experiment_arm": arm,
            "repeat_index": 1,
            "execution_status": "completed",
            "usage_status": "complete",
            "outcome": {"partial_credit_score": score, "partial_credit_max": 100},
            "cost": {"estimated_cost_usd": cost},
        }

    result = assess(plan, [receipt("a", float("nan"), 0)], [receipt("b", 100, -1)], "development")
    assert result["decision"] == "inconclusive"
    assert any("bounded score" in reason for reason in result["reasons"])
    assert any("nonnegative" in reason for reason in result["reasons"])


def test_assess_run_loads_local_development_receipts(tmp_path):
    from awb.experiments.execution import assess_run

    plan, _, _, tasks_dir = _plan(tmp_path)
    runs_dir = tmp_path / "runs"
    for arm, score in (("a", 0), ("b", 100)):
        run = runs_dir / arm
        run.mkdir(parents=True)
        (run / f"{arm}.json").write_text(
            json.dumps(
                {
                    "task_id": "BF-001",
                    "model": "claude-test-model",
                    "effective_config_hash": plan["spec"][f"config_{arm}_hash"],
                    "task_definition_hash": plan["spec"]["task_hashes"]["BF-001"],
                    "experiment_plan_hash": plan["plan_hash"],
                    "experiment_split": "development",
                    "experiment_arm": arm,
                    "repeat_index": 1,
                    "execution_status": "completed",
                    "usage_status": "complete",
                    "outcome": {"partial_credit_score": score, "partial_credit_max": 100},
                }
            )
        )
    result = assess_run(plan, runs_dir, tasks_dir, "development")
    assert result["paired_tasks"] == 1
    assert not any("Unverified imported evidence" in reason for reason in result["reasons"])


def test_assess_run_requires_matching_holdout_consumption_record(monkeypatch, tmp_path):
    from awb.experiments.execution import assess_run

    plan, _, _, tasks_dir = _plan(tmp_path)
    holdout = tasks_dir / "BF-002.yaml"
    _task(holdout, "BF-002")
    plan = create_plan(
        {
            **plan["spec"],
            "holdout_tasks": ["BF-002"],
            "task_hashes": {
                **plan["spec"]["task_hashes"],
                "BF-002": __import__("hashlib").sha256(holdout.read_bytes()).hexdigest(),
            },
        }
    )
    monkeypatch.setattr("awb.experiments.execution._validate_holdout_controls", lambda paths: None)
    monkeypatch.setattr(
        "awb.experiments.execution._require_development_confirmation", lambda runs_dir, plan: None
    )
    with pytest.raises(ValueError, match="consumption record"):
        assess_run(plan, tmp_path / "runs", tasks_dir, "holdout")


def test_runtime_preflight_rejects_missing_allowed_environment(monkeypatch, tmp_path):
    from awb.experiments.execution import _preflight_runtime, config_snapshot

    _, config_b = _configs(tmp_path)
    snapshot = config_snapshot(config_b)
    monkeypatch.delenv("DECLARED_MISSING_TOKEN", raising=False)
    with pytest.raises(ValueError, match="DECLARED_MISSING_TOKEN"):
        _preflight_runtime(
            (snapshot, snapshot),
            "claude-test-model",
            ("DECLARED_MISSING_TOKEN",),
            tmp_path / "runs",
        )


def test_runtime_preflight_rejects_missing_cli(monkeypatch, tmp_path):
    from awb.experiments.execution import _preflight_runtime, config_snapshot

    _, config_b = _configs(tmp_path)
    snapshot = config_snapshot(config_b)
    monkeypatch.setattr("awb.experiments.execution.shutil.which", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="not available"):
        _preflight_runtime((snapshot, snapshot), "claude-test-model", (), tmp_path / "runs")


def test_runtime_preflight_runs_before_attempt_marker(monkeypatch, tmp_path):
    from awb.experiments.execution import execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    called = []

    def reject(*args):
        raise ValueError("preflight rejected")

    monkeypatch.setattr("awb.experiments.execution._preflight_runtime", reject)
    monkeypatch.setattr(
        "awb.experiments.execution._execute_attempt", lambda **kwargs: called.append(kwargs)
    )
    runs_dir = tmp_path / "runs"
    with pytest.raises(ValueError, match="preflight rejected"):
        execute_plan(plan, config_a, config_b, tasks_dir, "development", runs_dir)
    assert called == []
    assert not (runs_dir / ".experiment-attempts").exists()


def test_attempt_passes_stage_and_whole_attempt_deadlines(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from awb.experiments.execution import _execute_attempt

    captured = {}

    class FakeRunner:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.recorder = None
            self._run_id = ""

        async def run_all(self):
            return [SimpleNamespace(run_id="run1", task_id="BF-001", tool="claude-code-custom")]

    monkeypatch.setattr("awb.core.runner.BenchmarkRunner", FakeRunner)
    _execute_attempt(
        task=SimpleNamespace(id="BF-001"),
        arm="a",
        repeat_index=1,
        config_dir=tmp_path,
        model="claude-test-model",
        timeout_seconds=120,
        setup_timeout_seconds=30,
        verification_timeout_seconds=40,
        attempt_timeout_seconds=190,
        allowed_env=(),
        home_dir=tmp_path / "home",
        tmp_dir=tmp_path / "tmp",
        runs_dir=tmp_path / "runs",
        run_id="run",
        tasks_dir=tmp_path / "tasks",
    )
    assert captured["timeout_override"] == 120
    assert captured["setup_timeout_seconds"] == 30
    assert captured["verification_timeout_seconds"] == 40
    assert captured["experiment_timeout_seconds"] == 190


def test_adapter_marks_unobserved_model_unknown(monkeypatch, tmp_path):
    import asyncio

    from awb.adapters.base import ToolResult
    from awb.adapters.claude_code import ClaudeCodeCustomAdapter
    from awb.experiments.execution import _ModelPinnedClaudeAdapter

    async def empty_model(*args, **kwargs):
        return ToolResult(success=True, model="")

    monkeypatch.setattr(ClaudeCodeCustomAdapter, "execute", empty_model)
    home, temp = tmp_path / "home", tmp_path / "tmp"
    home.mkdir()
    temp.mkdir()
    adapter = _ModelPinnedClaudeAdapter(tmp_path, "claude-test-model", home_dir=home, tmp_dir=temp)
    result = asyncio.run(adapter.execute("prompt", tmp_path))
    assert result.model == "unknown"


def test_failed_observed_receipt_is_not_rewritten_or_rerun(monkeypatch, tmp_path):
    from awb.experiments.execution import execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    calls = []

    def failed_attempt(**kwargs):
        calls.append(kwargs["arm"])
        run_dir = kwargs["runs_dir"] / f"{kwargs['run_id']}_run1"
        run_dir.mkdir(parents=True)
        path = run_dir / f"{kwargs['task'].id}_claude-code-custom.json"
        path.write_text(
            json.dumps(
                {
                    "task_id": kwargs["task"].id,
                    "tool": "claude-code-custom",
                    "run_id": f"{kwargs['run_id']}_run1",
                    "model": "observed-other-model",
                    "execution_status": "timed_out",
                    "outcome": {
                        "success": False,
                        "partial_credit_score": 0,
                        "partial_credit_max": 100,
                    },
                }
            )
        )
        return path

    monkeypatch.setattr("awb.experiments.execution._execute_attempt", failed_attempt)
    first = execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")
    assert len(first["executed_attempts"]) == 1
    receipt = first["executed_attempts"][0]
    assert receipt["model"] == "observed-other-model"
    assert receipt["execution_status"] == "timed_out"
    assert receipt["requested_model"] == "claude-test-model"
    with pytest.raises(ValueError, match="model differs"):
        execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")
    assert len(calls) == 1


def test_holdout_claim_survives_replanning_threshold(tmp_path):
    from awb.experiments.execution import _claim_holdout

    plan, _, _, _ = _plan(tmp_path)
    _claim_holdout(tmp_path / "runs", plan)
    changed = create_plan({**plan["spec"], "minimum_delta": plan["spec"]["minimum_delta"] + 1})
    with pytest.raises(ValueError, match="already consumed"):
        _claim_holdout(tmp_path / "runs", changed)


def test_holdout_needs_complete_eligible_development_result(tmp_path):
    from awb.experiments.execution import _require_development_confirmation

    plan, _, _, _ = _plan(tmp_path)
    with pytest.raises(ValueError, match="development attempts"):
        _require_development_confirmation(tmp_path / "runs", plan)


def test_marker_creation_is_exclusive(tmp_path):
    from awb.experiments.execution import _create_marker

    marker = tmp_path / "marker.json"
    _create_marker(marker, ("BF-001", "a", 1))
    with pytest.raises(ValueError, match="Ambiguous"):
        _create_marker(marker, ("BF-001", "a", 1))


def test_all_selected_task_hashes_are_checked_before_any_attempt(monkeypatch, tmp_path):
    from awb.experiments.execution import execute_plan

    plan, config_a, config_b, tasks_dir = _plan(tmp_path)
    plan["spec"]["development_tasks"] = ["BF-001", "BF-002"]
    plan["spec"]["task_hashes"]["BF-002"] = "c" * 64
    plan = create_plan(plan["spec"])
    calls = []
    monkeypatch.setattr(
        "awb.experiments.execution._execute_attempt", lambda **kwargs: calls.append(kwargs)
    )

    with pytest.raises(ValueError, match="missing"):
        execute_plan(plan, config_a, config_b, tasks_dir, "development", tmp_path / "runs")
    assert calls == []
