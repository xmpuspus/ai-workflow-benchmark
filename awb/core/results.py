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
        with open(path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        return path

    def load_run(self, run_dir: Path) -> list[RunResult]:
        """Load all result JSONs from a single run directory."""
        results = []
        for json_file in sorted(run_dir.glob("*.json")):
            with open(json_file) as f:
                data = json.load(f)
            results.append(_dict_to_result(data))
        return results

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
