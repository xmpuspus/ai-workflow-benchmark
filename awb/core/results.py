"""Write and read structured JSON results."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path

from awb.core.config import (
    RESULTS_DIR,
    CriterionResult,
    RunCost,
    RunEnvironment,
    RunError,
    RunExecution,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
    WorkflowInfo,
)


class ResultRecorder:
    def __init__(self, results_dir: Path | None = None) -> None:
        self.results_dir = results_dir or RESULTS_DIR

    def save(self, result: RunResult) -> Path:
        """Write result as JSON and append to JSONL. Returns the JSON file path."""
        run_dir = self.results_dir / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{result.task_id}_{result.tool}.json"
        data = result.to_dict()
        # v2 schema: schema_version is the canonical version key. Keep 'version'
        # for one release for backward compat with v1.x readers.
        data["schema_version"] = 2
        data["version"] = "1.0"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        # Also append to JSONL for fast batch loading
        self._append_jsonl(result.run_id, data)
        return path

    def _append_jsonl(self, run_id: str, data: dict) -> None:
        """Append a result to the run's JSONL file.

        Uses fcntl.LOCK_EX so that concurrent --parallel writers (and any
        other process appending to the same JSONL) serialize at the OS level.
        Result records can exceed PIPE_BUF (~4KB), so the POSIX atomic-append
        guarantee does not apply and interleaving would silently corrupt rows.
        """
        import re

        match = re.match(r"^(.+)_run\d+$", run_id)
        base_id = match.group(1) if match else run_id
        jsonl_path = self.results_dir / f"{base_id}.jsonl"
        line = json.dumps(data) + "\n"
        with open(jsonl_path, "a") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def load_jsonl(self, base_run_id: str) -> list[RunResult]:
        """Load all results from a JSONL file for fast batch access."""
        jsonl_path = self.results_dir / f"{base_run_id}.jsonl"
        if not jsonl_path.exists():
            return []
        results = []
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    results.append(_dict_to_result(data))
        return results

    def load_run(self, run_dir: Path) -> list[RunResult]:
        """Load all result JSONs from a single run directory."""
        results = []
        for json_file in sorted(run_dir.glob("*.json")):
            with open(json_file) as f:
                data = json.load(f)
            results.append(_dict_to_result(data))
        return results

    def has_result(self, run_id: str, task_id: str, tool: str) -> bool:
        """Return True if the result file for this run/task/tool exists."""
        return (self.results_dir / run_id / f"{task_id}_{tool}.json").exists()

    def load_single(self, run_id: str, task_id: str, tool: str) -> RunResult | None:
        """Load and return a single result if it exists, None otherwise."""
        path = self.results_dir / run_id / f"{task_id}_{tool}.json"
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
        return _dict_to_result(data)

    def load_all_runs(self) -> dict[str, list[RunResult]]:
        """Load all runs, keyed by run_id."""
        runs: dict[str, list[RunResult]] = {}
        if not self.results_dir.exists():
            return runs
        for run_dir in sorted(self.results_dir.iterdir()):
            if run_dir.is_dir():
                results = self.load_run(run_dir)
                if results:
                    runs[run_dir.name] = results
        return runs

    def find_incomplete_run(
        self,
        tool: str,
        expected_tasks: int | None = None,
        *,
        task_ids: list[str] | None = None,
        requested_runs: int = 1,
        task_set_hash: str = "",
        identity_by_task: dict[str, dict[str, object]] | None = None,
    ) -> str | None:
        """Find the newest compatible experiment missing a task/repeat result.

        ``identity_by_task`` is optional for callers using the legacy counting
        API. When supplied, every recorded result must carry the exact current
        execution identity. Empty legacy identity fields are not compatible.
        An empty expected model means the current runner did not pin a model,
        so the adapter's observed model is not used as a resume constraint.
        """
        if not self.results_dir.exists():
            return None

        # Group run directories by base_id
        import re

        base_ids: dict[str, list[Path]] = {}
        for run_dir in sorted(self.results_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            name = run_dir.name
            match = re.match(r"^(.+)_run(\d+)$", name)
            if not match:
                continue
            base_id = match.group(1)
            base_ids.setdefault(base_id, []).append(run_dir)

        for base_id, run_dirs in base_ids.items():
            if task_ids is None:
                total_files = sum(len(list(path.glob(f"*_{tool}.json"))) for path in run_dirs)
                if total_files and expected_tasks is not None and total_files < expected_tasks:
                    return base_id
                continue

            found_any = False
            compatible = True
            complete = True
            for repeat in range(1, requested_runs + 1):
                run_id = f"{base_id}_run{repeat}"
                for task_id in task_ids:
                    result = self.load_single(run_id, task_id, tool)
                    if result is None:
                        complete = False
                        continue
                    found_any = True
                    if task_set_hash and result.task_set_hash != task_set_hash:
                        compatible = False
                        break
                    expected_identity = (identity_by_task or {}).get(task_id)
                    if identity_by_task is not None and (
                        expected_identity is None
                        or not _matches_resume_identity(result, expected_identity)
                    ):
                        compatible = False
                        break
                if not compatible:
                    break
            if found_any and compatible and not complete:
                return base_id

        return None


def _matches_resume_identity(result: RunResult, expected: dict[str, object]) -> bool:
    """Return whether a saved result proves it belongs to the current cohort."""
    for field, expected_value in expected.items():
        if field == "model" and _unknown_identity_value(expected_value):
            continue
        if _unknown_identity_value(expected_value):
            return False
        actual_value = getattr(result, field, None)
        if _unknown_identity_value(actual_value) or actual_value != expected_value:
            return False
    return True


def _unknown_identity_value(value: object) -> bool:
    return value is None or value == "" or value == "unknown" or value == {}


def _dict_to_result(data: dict) -> RunResult:
    """Deserialize a result dict into a RunResult."""
    outcome_data = data["outcome"]
    breakdown = [
        CriterionResult(
            criterion=c["criterion"],
            points_earned=c["points_earned"],
            points_possible=c["points_possible"],
            passed=c["passed"],
        )
        for c in outcome_data.get("breakdown", [])
    ]

    metrics_data = data.get("metrics", {})
    cost_data = data.get("cost", {})
    quality_data = data.get("quality", {})
    env_data = data.get("environment", {})
    wf_data = data.get("workflow")

    workflow = None
    if wf_data:
        workflow = WorkflowInfo(
            name=wf_data.get("name", ""),
            descriptor_hash=wf_data.get("descriptor_hash", ""),
            tool=wf_data.get("tool", ""),
            model=wf_data.get("model", ""),
            mode=wf_data.get("mode", ""),
            config_hash=wf_data.get("config_hash", ""),
        )

    error_data = outcome_data.get("error")
    error = None
    if isinstance(error_data, dict):
        error = RunError(
            exc_type=error_data.get("exc_type", ""),
            exc_message=error_data.get("exc_message", ""),
            traceback_tail=error_data.get("traceback_tail", ""),
        )

    return RunResult(
        task_id=data["task_id"],
        tool=data["tool"],
        tool_version=data.get("tool_version", ""),
        model=data.get("model", ""),
        run_id=data["run_id"],
        timestamp=data["timestamp"],
        outcome=RunOutcome(
            success=outcome_data["success"],
            partial_credit_score=outcome_data["partial_credit_score"],
            partial_credit_max=outcome_data["partial_credit_max"],
            breakdown=breakdown,
            error=error,
        ),
        metrics=RunMetrics(
            wall_clock_seconds=metrics_data.get("wall_clock_seconds", 0),
            iteration_count=metrics_data.get("iteration_count", 0),
            human_interventions=metrics_data.get("human_interventions", 0),
            tool_calls=metrics_data.get("tool_calls", {}),
            files_modified=metrics_data.get("files_modified", 0),
            lines_changed=metrics_data.get("lines_changed", 0),
        ),
        cost=RunCost(
            input_tokens=cost_data.get("input_tokens", 0),
            output_tokens=cost_data.get("output_tokens", 0),
            cache_read_tokens=cost_data.get("cache_read_tokens", 0),
            cache_creation_tokens=cost_data.get("cache_creation_tokens", 0),
            thinking_tokens=cost_data.get("thinking_tokens", 0),
            estimated_cost_usd=cost_data.get("estimated_cost_usd", 0),
            estimated_credits=cost_data.get("estimated_credits"),
            usage_status=cost_data.get("usage_status", "unknown"),
        ),
        quality=RunQuality(
            lint_delta=quality_data.get("lint_delta", 0),
            security_delta=quality_data.get("security_delta", 0),
            test_regressions=quality_data.get("test_regressions", 0),
            baseline_security_issues=quality_data.get("baseline_security_issues"),
            post_security_issues=quality_data.get("post_security_issues"),
            lint_status=quality_data.get("lint_status", "missing"),
            security_status=quality_data.get("security_status", "missing"),
            test_regressions_status=quality_data.get("test_regressions_status", "missing"),
        ),
        environment=RunEnvironment(
            os=env_data.get("os", ""),
            hardware=env_data.get("hardware", ""),
            python_version=env_data.get("python_version", ""),
            awb_version=env_data.get("awb_version", ""),
            adapter_version=env_data.get("adapter_version", ""),
            pip_freeze_hash=env_data.get("pip_freeze_hash", ""),
        ),
        workflow=workflow,
        task_set_hash=data.get("task_set_hash", ""),
        trace_path=data.get("trace_path", ""),
        execution=RunExecution(
            status=data.get("execution", {}).get("status", "unknown"),
            stage=data.get("execution", {}).get("stage", "unknown"),
            termination_reason=data.get("execution", {}).get("termination_reason", ""),
            tool_success=data.get("execution", {}).get("tool_success"),
            tool_exit_code=data.get("execution", {}).get("tool_exit_code"),
        ),
        task_definition_hash=data.get("task_definition_hash", ""),
        evaluator_version=data.get("evaluator_version", ""),
        effective_config_hash=data.get("effective_config_hash", ""),
        adapter_version=data.get("adapter_version", ""),
        execution_mode=data.get("execution_mode", "host"),
        environment_fingerprint=data.get("environment_fingerprint", ""),
        budget_fingerprint=data.get("budget_fingerprint", ""),
        cohort_id=data.get("cohort_id", ""),
        loaded_instruction_files=data.get("loaded_instruction_files", []),
        allowed_edit_paths=data.get("allowed_edit_paths", []),
        effective_input_manifest=data.get("effective_input_manifest", {}),
        environment_manifest=data.get("environment_manifest", {}),
        cohort_manifest=data.get("cohort_manifest", {}),
        experiment_plan_hash=data.get("experiment_plan_hash", ""),
        experiment_split=data.get("experiment_split", ""),
        experiment_arm=data.get("experiment_arm", ""),
        repeat_index=data.get("repeat_index"),
        requested_model=data.get("requested_model", ""),
        experiment_attempt_status=data.get("experiment_attempt_status", ""),
        experiment_state_policy=data.get("experiment_state_policy", ""),
        configured_instruction_files=data.get("configured_instruction_files", []),
    )
