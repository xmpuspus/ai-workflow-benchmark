from __future__ import annotations

import asyncio
import hashlib
import shlex
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.config import RunEnvironment
from awb.core.results import ResultRecorder
from awb.core.runner import BenchmarkRunner, _delta_measurement_status
from awb.core.subprocesses import run_shell, stop_process_group
from awb.core.timeout import TaskTimeoutError
from awb.verification.security_scanner import measure_security_issues


class _FailedAfterEditAdapter(ToolAdapter):
    name = "codex-cli"
    display_name = "Failed after edit"

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=1800, on_event=None):
        (workspace / "partial.py").write_text("fixed = True\n")
        (workspace / "AGENTS.override.md").write_text("agent changed instructions\n")
        return ToolResult(success=False, raw_output="crashed", exit_code=9)

    def check_available(self):
        return True

    def get_config_hash(self):
        return "config-hash"


def _runner(tmp_path: Path, sample_task, adapter: ToolAdapter) -> BenchmarkRunner:
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.tool = adapter.name
    runner.tasks = [sample_task]
    runner.runs = 1
    runner.parallel = False
    runner.timeout_override = None
    runner.workflow = None
    runner.resume = False
    runner.concurrency = 1
    runner.adaptive = False
    runner.progressive = False
    runner.execution_mode = "host"
    runner.container_image = ""
    runner.setup_timeout_seconds = 30
    runner.verification_timeout_seconds = 30
    runner.experiment_timeout_seconds = None
    runner._experiment_deadline = None
    runner._adapter = adapter
    runner._run1_times = {}
    runner._run_id = "evidence"
    runner._task_set_hash = "ab" * 32
    runner._environment = RunEnvironment(os="test", hardware="test", pip_freeze_hash="deps")
    runner.recorder = ResultRecorder(tmp_path / "results")

    class Repo:
        async def prepare(self, task, run_id=None):
            workspace = tmp_path / "workspace"
            workspace.mkdir(exist_ok=True)
            (workspace / "AGENTS.override.md").write_text("instructions\n")
            return workspace

        def capture_change_snapshot(self, workspace):
            return {"AGENTS.override.md": b"instructions\n"}

        def get_modified_files_since(self, workspace, baseline):
            return ["partial.py"] if (workspace / "partial.py").exists() else []

        def get_lines_changed_since(self, workspace, baseline):
            return 1 if (workspace / "partial.py").exists() else 0

        async def cleanup(self, workspace):
            return None

    runner.repo_manager = Repo()
    return runner


@pytest.mark.asyncio
async def test_tool_failure_is_preserved_separately_from_patch_verification(
    tmp_path, sample_task, monkeypatch
):
    runner = _runner(tmp_path, sample_task, _FailedAfterEditAdapter())
    monkeypatch.setattr("awb.core.runner._count_baseline", lambda *args: asyncio.sleep(0, result=0))
    monkeypatch.setattr(
        "awb.core.runner.run_tests", lambda *args: asyncio.sleep(0, result=(True, ""))
    )
    monkeypatch.setattr(
        "awb.core.runner.evaluate_partial_credit",
        lambda *args, **kwargs: asyncio.sleep(0, result=(100, 100, [])),
    )
    monkeypatch.setattr(
        "awb.core.runner.measure_lint_issues",
        lambda *args: asyncio.sleep(0, result=(0, "measured_clean")),
    )
    monkeypatch.setattr(
        "awb.core.runner.measure_security_issues",
        lambda *args: asyncio.sleep(0, result=(0, "missing")),
    )

    result = await runner.run_single(sample_task, run_id="evidence_run1")

    assert result.outcome.success is True
    assert result.execution.status == "failed"
    assert result.execution.tool_success is False
    assert result.execution.tool_exit_code == 9
    assert result.execution.stage == "complete"
    assert result.cost.usage_status == "unknown"
    assert result.metrics.files_modified == 1
    assert result.loaded_instruction_files == ["AGENTS.override.md"]
    expected_hash = hashlib.sha256(b"instructions\n").hexdigest()
    instruction_hashes = result.effective_input_manifest["instruction_hashes"]
    assert instruction_hashes["AGENTS.override.md"] == expected_hash
    assert result.environment_manifest["ambient_credentials_forwarded"] is None
    assert result.cohort_manifest["cohort_id"] == result.cohort_id
    assert result.quality.security_status == "missing"
    assert result.quality.baseline_security_issues is None
    assert result.quality.post_security_issues is None
    assert result.quality.test_regressions == 0
    assert result.quality.test_regressions_status == "measured_clean"


def test_result_roundtrip_preserves_execution_identity_and_measurement_statuses(
    tmp_path, sample_result
):
    sample_result.execution.status = "timed_out"
    sample_result.execution.termination_reason = "agent_timeout"
    sample_result.cost.usage_status = "partial"
    sample_result.quality.lint_status = "missing"
    sample_result.quality.security_status = "failed"
    sample_result.quality.baseline_security_issues = 4
    sample_result.quality.post_security_issues = 4
    sample_result.quality.test_regressions_status = "measured_findings"
    sample_result.task_definition_hash = "1" * 64
    sample_result.effective_config_hash = "2" * 64
    sample_result.environment_fingerprint = "3" * 64
    sample_result.budget_fingerprint = "4" * 64
    sample_result.cohort_id = "5" * 64
    sample_result.loaded_instruction_files = ["AGENTS.override.md"]
    sample_result.allowed_edit_paths = ["src/**"]

    recorder = ResultRecorder(tmp_path)
    loaded = (
        recorder.load_single(sample_result.run_id, sample_result.task_id, sample_result.tool)
        if recorder.save(sample_result)
        else None
    )

    assert loaded is not None
    assert loaded.execution.status == "timed_out"
    assert loaded.cost.usage_status == "partial"
    assert loaded.quality.security_status == "failed"
    assert loaded.quality.baseline_security_issues == 4
    assert loaded.quality.post_security_issues == 4
    assert loaded.cohort_id == "5" * 64
    assert loaded.loaded_instruction_files == ["AGENTS.override.md"]
    assert loaded.allowed_edit_paths == ["src/**"]


@pytest.mark.asyncio
async def test_runner_preserves_unchanged_nonzero_security_counts(
    tmp_path, sample_task, monkeypatch
):
    runner = _runner(tmp_path, sample_task, _FailedAfterEditAdapter())
    monkeypatch.setattr("awb.core.runner._count_baseline", lambda *args: asyncio.sleep(0, result=0))
    monkeypatch.setattr(
        "awb.core.runner.run_tests", lambda *args: asyncio.sleep(0, result=(True, ""))
    )
    monkeypatch.setattr(
        "awb.core.runner.evaluate_partial_credit",
        lambda *args, **kwargs: asyncio.sleep(0, result=(100, 100, [])),
    )
    monkeypatch.setattr(
        "awb.core.runner.measure_lint_issues",
        lambda *args: asyncio.sleep(0, result=(0, "measured_clean")),
    )
    monkeypatch.setattr(
        "awb.core.runner.measure_security_issues",
        lambda *args: asyncio.sleep(0, result=(4, "measured_findings")),
    )

    result = await runner.run_single(sample_task, run_id="security_counts_run1")

    assert result.quality.security_delta == 0
    assert result.quality.security_status == "measured_clean"
    assert result.quality.baseline_security_issues == 4
    assert result.quality.post_security_issues == 4


def test_repeat_aware_resume_requires_every_requested_identity(tmp_path, sample_result):
    recorder = ResultRecorder(tmp_path)
    sample_result.run_id = "experiment_run1"
    sample_result.task_set_hash = "a" * 64
    recorder.save(sample_result)

    assert (
        recorder.find_incomplete_run(
            sample_result.tool,
            task_ids=[sample_result.task_id],
            requested_runs=3,
            task_set_hash="a" * 64,
        )
        == "experiment"
    )
    assert (
        recorder.find_incomplete_run(
            sample_result.tool,
            task_ids=[sample_result.task_id],
            requested_runs=1,
            task_set_hash="a" * 64,
        )
        is None
    )
    assert (
        recorder.find_incomplete_run(
            sample_result.tool,
            task_ids=[sample_result.task_id],
            requested_runs=3,
            task_set_hash="b" * 64,
        )
        is None
    )


@pytest.mark.parametrize(
    "field",
    [
        "task_definition_hash",
        "evaluator_version",
        "effective_config_hash",
        "adapter_version",
        "model",
        "execution_mode",
        "environment_fingerprint",
        "budget_fingerprint",
        "cohort_manifest",
    ],
)
def test_resume_rejects_changed_or_unknown_execution_identity(tmp_path, sample_result, field):
    recorder = ResultRecorder(tmp_path)
    sample_result.run_id = "experiment_run1"
    sample_result.task_set_hash = "a" * 64
    sample_result.task_definition_hash = "task-v1"
    sample_result.evaluator_version = "evaluator-v1"
    sample_result.effective_config_hash = "config-v1"
    sample_result.adapter_version = "adapter-v1"
    sample_result.model = "model-v1"
    sample_result.execution_mode = "host"
    sample_result.environment_fingerprint = "environment-v1"
    sample_result.budget_fingerprint = "budget-v1"
    sample_result.cohort_manifest = {
        "selected_task_ids": [sample_result.task_id],
        "selected_task_definition_hashes": {sample_result.task_id: "task-v1"},
        "requested_repeats": 2,
    }
    recorder.save(sample_result)
    expected = {
        key: getattr(sample_result, key)
        for key in (
            "task_definition_hash",
            "evaluator_version",
            "effective_config_hash",
            "adapter_version",
            "model",
            "execution_mode",
            "environment_fingerprint",
            "budget_fingerprint",
            "cohort_manifest",
        )
    }
    expected[field] = {} if field == "cohort_manifest" else f"changed-{field}"

    assert (
        recorder.find_incomplete_run(
            sample_result.tool,
            task_ids=[sample_result.task_id],
            requested_runs=2,
            task_set_hash=sample_result.task_set_hash,
            identity_by_task={sample_result.task_id: expected},
        )
        is None
    )


def test_resume_does_not_require_model_when_current_run_does_not_declare_one(
    tmp_path, sample_result
):
    recorder = ResultRecorder(tmp_path)
    sample_result.run_id = "experiment_run1"
    sample_result.task_set_hash = "a" * 64
    sample_result.model = "observed-model"
    recorder.save(sample_result)

    assert (
        recorder.find_incomplete_run(
            sample_result.tool,
            task_ids=[sample_result.task_id],
            requested_runs=2,
            task_set_hash=sample_result.task_set_hash,
            identity_by_task={sample_result.task_id: {"model": ""}},
        )
        == "experiment"
    )


@pytest.mark.asyncio
async def test_stage_deadline_interrupts_work():
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner._experiment_deadline = None
    with pytest.raises(TaskTimeoutError):
        await runner._run_stage(asyncio.sleep(1), 0.01, "BF-001", "verification_timeout")


@pytest.mark.asyncio
async def test_whole_experiment_deadline_stops_before_next_repeat(sample_task):
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.tasks = [sample_task]
    runner.runs = 3
    runner.experiment_timeout_seconds = 0.01
    runner.adaptive = False
    runner.progressive = False
    runner.parallel = False
    runner._run_id = "deadline"
    calls = []

    async def one_run(*args, **kwargs):
        calls.append(args[2])
        await asyncio.sleep(0.02)
        return []

    runner._run_sequential = one_run
    results = await runner.run_all()
    assert results == []
    assert calls == [1]


@pytest.mark.asyncio
async def test_expired_deadline_leaves_sequential_attempts_unstarted_and_resumable(
    tmp_path, sample_task
):
    runner = _runner(tmp_path, sample_task, _FailedAfterEditAdapter())
    runner._experiment_deadline = time.monotonic() - 1
    calls = []

    async def run_single(task, run_id=None, run_num=1):
        calls.append(task.id)
        raise AssertionError("expired attempts must not launch")

    runner.run_single = run_single
    results = await runner._run_sequential(
        [sample_task], "deadline_run1", 1, 1, 0, 0, time.monotonic()
    )

    assert results == []
    assert calls == []
    assert not runner.recorder.has_result("deadline_run1", sample_task.id, runner.tool)


@pytest.mark.asyncio
async def test_parallel_waiter_does_not_launch_after_deadline(tmp_path, sample_task, sample_result):
    runner = _runner(tmp_path, sample_task, _FailedAfterEditAdapter())
    second = replace(sample_task, id="BF-999")
    runner.tasks = [sample_task, second]
    runner.concurrency = 1
    runner._experiment_deadline = time.monotonic() + 60
    calls = []

    async def run_single(task, run_id=None, run_num=1):
        calls.append(task.id)
        runner._experiment_deadline = time.monotonic() - 1
        await asyncio.sleep(0)
        return replace(sample_result, task_id=task.id, run_id=run_id)

    runner.run_single = run_single
    results = await runner._run_parallel(
        runner.tasks, run_id="deadline_run1", run_num=1, total_tasks=2
    )

    assert calls == [sample_task.id]
    assert [result.task_id for result in results] == [sample_task.id]
    assert not runner.recorder.has_result("deadline_run1", second.id, runner.tool)


@pytest.mark.asyncio
async def test_missing_security_binary_has_failed_measurement_status(tmp_path):
    count, status = await measure_security_issues(
        ["this-binary-does-not-exist-9999 --scan ."], tmp_path
    )
    assert count == 0
    assert status == "failed"


@pytest.mark.asyncio
async def test_masked_security_command_has_failed_measurement_status(tmp_path):
    count, status = await measure_security_issues(["bandit -r . || true"], tmp_path)
    assert count == 0
    assert status == "failed"


def test_delta_status_requires_both_measurements():
    assert _delta_measurement_status("missing", "measured_clean", 0) == "missing"
    assert _delta_measurement_status("failed", "measured_clean", 0) == "failed"
    assert _delta_measurement_status("measured_clean", "measured_clean", 0) == "measured_clean"
    assert _delta_measurement_status("measured_clean", "measured_clean", 1) == "measured_findings"


@pytest.mark.skipif(not hasattr(__import__("os"), "killpg"), reason="POSIX process groups required")
def test_shell_timeout_stops_descendant_process(tmp_path):
    marker = tmp_path / "descendant-survived"
    child_code = f"import time,pathlib; time.sleep(1); pathlib.Path({str(marker)!r}).touch()"
    command = (
        f"{shlex.quote(sys.executable)} -c {shlex.quote(child_code)} & "
        f"{shlex.quote(sys.executable)} -c 'import time; time.sleep(30)'"
    )
    result = asyncio.run(run_shell(command, cwd=tmp_path, timeout=0.1))
    assert result.exit_code == 124
    asyncio.run(asyncio.sleep(1.2))
    assert not marker.exists()


@pytest.mark.asyncio
async def test_group_cleanup_signals_descendants_after_parent_exit(monkeypatch):
    class ExitedParent:
        pid = 43210
        returncode = 0

    signals = []
    monkeypatch.setattr(
        "awb.core.subprocesses.os.killpg", lambda pid, sig: signals.append((pid, sig))
    )
    await stop_process_group(ExitedParent())
    assert len(signals) == 2


def test_container_command_has_narrow_mounts_and_no_ambient_environment(tmp_path, monkeypatch):
    from awb.core.container import build_container_command

    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-copy")
    command = build_container_command(
        image="awb-test:latest",
        project_root=tmp_path / "source",
        results_dir=tmp_path / "results",
        cli_args=["run", "fake", "--yes"],
    )
    joined = " ".join(command)
    assert str(Path.home()) not in joined
    assert "AWS_SECRET_ACCESS_KEY" not in joined
    assert command.count("--mount") == 2
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cpus=2" in command
    assert "--memory=4g" in command
    assert "--pids-limit=256" in command
    assert command[-4:] == ["run", "fake", "--yes", "--inside-container"]


def test_custom_task_path_is_translated_or_rejected(tmp_path):
    import click

    from awb.commands.run import _path_inside_container

    project = tmp_path / "project"
    tasks = project / "private" / "tasks"
    tasks.mkdir(parents=True)
    assert _path_inside_container(tasks, project) == "/opt/awb/private/tasks"
    with pytest.raises(click.ClickException):
        _path_inside_container(tmp_path / "outside", project)


def test_container_can_mount_an_explicit_external_task_pack_read_only(tmp_path):
    from awb.core.container import build_container_command

    tasks = tmp_path / "private-tasks"
    tasks.mkdir()
    command = build_container_command(
        image="test-image",
        project_root=tmp_path / "package",
        results_dir=tmp_path / "results",
        cli_args=["run", "codex-cli"],
        input_mounts=[(tasks, "/inputs/tasks")],
    )
    assert f"type=bind,src={tasks},dst=/inputs/tasks,readonly" in command


def test_container_rejects_home_as_task_input(tmp_path):
    from awb.core.container import build_container_command

    with pytest.raises(ValueError, match="broad"):
        build_container_command(
            image="test-image",
            project_root=tmp_path,
            results_dir=tmp_path / "results",
            cli_args=["run"],
            input_mounts=[(Path.home(), "/inputs/tasks")],
        )


def test_selected_tasks_share_cohort_budget_but_keep_individual_definitions(tmp_path, sample_task):
    from dataclasses import replace

    second = replace(
        sample_task,
        id="BF-999",
        constraints=replace(
            sample_task.constraints, timeout_seconds=sample_task.constraints.timeout_seconds + 10
        ),
    )
    runner = _runner(tmp_path, sample_task, _FailedAfterEditAdapter())
    runner.tasks = [sample_task, second]
    runner.runs = 2
    first_identity = runner._identity_fields(sample_task, None)
    second_identity = runner._identity_fields(second, None)
    assert first_identity["budget_fingerprint"] == second_identity["budget_fingerprint"]
    assert first_identity["cohort_id"] == second_identity["cohort_id"]
    assert first_identity["task_definition_hash"] != second_identity["task_definition_hash"]
    assert first_identity["cohort_manifest"]["selected_task_ids"] == sorted(
        [sample_task.id, second.id]
    )
    assert first_identity["cohort_manifest"]["selected_task_definition_hashes"] == {
        sample_task.id: first_identity["task_definition_hash"],
        second.id: second_identity["task_definition_hash"],
    }
    assert first_identity["cohort_manifest"]["requested_repeats"] == 2
    runner.runs = 3
    assert (
        runner._identity_fields(sample_task, None)["budget_fingerprint"]
        != first_identity["budget_fingerprint"]
    )
