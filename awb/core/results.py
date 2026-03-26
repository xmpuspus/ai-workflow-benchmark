"""Write and read structured JSON results."""
from __future__ import annotations

import json
from pathlib import Path

from awb.core.config import (
    RESULTS_DIR,
    CriterionResult,
    RunCost,
    RunEnvironment,
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
        """Write result as JSON. Returns the file path."""
        run_dir = self.results_dir / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{result.task_id}_{result.tool}.json"
        data = result.to_dict()
        data["version"] = "1.0"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

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
        self, tool: str, expected_tasks: int,
    ) -> str | None:
        """Find the most recent run_id for this tool that has fewer results than expected.

        Looks for directories matching *_run1 that contain {tool} results.
        Returns the base run_id (without _runN suffix) if incomplete, else None.
        """
        if not self.results_dir.exists():
            return None

        candidates: list[tuple[str, str]] = []  # (dir_name, base_id)
        for run_dir in sorted(self.results_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            name = run_dir.name
            if "_run1" not in name:
                continue
            # Check if this run has results for the requested tool
            tool_files = list(run_dir.glob(f"*_{tool}.json"))
            if not tool_files:
                continue
            base_id = name.rsplit("_run1", 1)[0]
            if len(tool_files) < expected_tasks:
                return base_id
            candidates.append((name, base_id))

        return None


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
            estimated_cost_usd=cost_data.get("estimated_cost_usd", 0),
        ),
        quality=RunQuality(
            lint_delta=quality_data.get("lint_delta", 0),
            security_delta=quality_data.get("security_delta", 0),
            test_regressions=quality_data.get("test_regressions", 0),
        ),
        environment=RunEnvironment(
            os=env_data.get("os", ""),
            hardware=env_data.get("hardware", ""),
        ),
        workflow=workflow,
    )
