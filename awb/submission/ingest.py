"""Parse and validate external submission JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import ValidationError, validate

from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
)
from awb.submission.schema import (
    Submission,
    SubmissionEnvironment,
    SubmissionModel,
    SubmissionRun,
    SubmissionRunCost,
    SubmissionRunMetrics,
    SubmissionRunOutcome,
    SubmissionRunQuality,
    SubmissionTaskResult,
    SubmissionTool,
)


def _load_submission_schema() -> dict:
    # Packaged copy (works in installed wheels) with fallback to repo layout
    packaged = Path(__file__).parent / "schema.json"
    repo = Path(__file__).parent.parent.parent / "results" / "submission-schema.json"
    schema_path = packaged if packaged.exists() else repo
    with schema_path.open() as f:
        return json.load(f)


def validate_submission(data: dict) -> list[str]:
    """Validate submission JSON against schema. Returns list of errors."""
    schema = _load_submission_schema()
    try:
        validate(instance=data, schema=schema)
        return []
    except ValidationError as e:
        return [e.message]


def parse_submission(data: dict) -> Submission:
    """Parse validated submission JSON into Submission dataclass."""
    sub = data["submission"]
    tool_raw = sub["tool"]
    model_raw = sub.get("model", {})
    env_raw = sub.get("environment", {})
    pricing = model_raw.get("pricing", {})

    tool = SubmissionTool(
        name=tool_raw["name"],
        version=tool_raw["version"],
        config_description=tool_raw.get("config_description", ""),
    )
    model = SubmissionModel(
        name=model_raw.get("name", ""),
        provider=model_raw.get("provider", ""),
        input_per_m_tokens=pricing.get("input_per_m_tokens", 0.0),
        output_per_m_tokens=pricing.get("output_per_m_tokens", 0.0),
    )
    environment = SubmissionEnvironment(
        os=env_raw.get("os", ""),
        hardware_class=env_raw.get("hardware_class", "other"),
        hardware_detail=env_raw.get("hardware_detail", ""),
        network=env_raw.get("network", "local"),
    )

    results = []
    for task_raw in data["results"]:
        runs = []
        for run_raw in task_raw["runs"]:
            outcome_raw = run_raw["outcome"]
            metrics_raw = run_raw["metrics"]
            cost_raw = run_raw["cost"]
            quality_raw = run_raw.get("quality", {})
            runs.append(
                SubmissionRun(
                    run_number=run_raw["run_number"],
                    timestamp=run_raw.get("timestamp", ""),
                    outcome=SubmissionRunOutcome(
                        success=outcome_raw["success"],
                        partial_credit_score=outcome_raw["partial_credit_score"],
                        partial_credit_max=outcome_raw["partial_credit_max"],
                    ),
                    metrics=SubmissionRunMetrics(
                        wall_clock_seconds=metrics_raw["wall_clock_seconds"],
                        iteration_count=metrics_raw["iteration_count"],
                        human_interventions=metrics_raw.get("human_interventions", 0),
                        files_modified=metrics_raw.get("files_modified", 0),
                        lines_changed=metrics_raw.get("lines_changed", 0),
                    ),
                    cost=SubmissionRunCost(
                        input_tokens=cost_raw.get("input_tokens", 0),
                        output_tokens=cost_raw.get("output_tokens", 0),
                        estimated_cost_usd=cost_raw["estimated_cost_usd"],
                    ),
                    quality=SubmissionRunQuality(
                        lint_delta=quality_raw.get("lint_delta", 0),
                        security_delta=quality_raw.get("security_delta", 0),
                        test_regressions=quality_raw.get("test_regressions", 0),
                    ),
                )
            )
        results.append(SubmissionTaskResult(task_id=task_raw["task_id"], runs=runs))

    return Submission(
        spec_version=data["spec_version"],
        tool=tool,
        model=model,
        environment=environment,
        awb_version=sub.get("awb_version", ""),
        task_set_hash=sub.get("task_set_hash", ""),
        submitter=sub.get("submitter", "anonymous"),
        results=results,
    )


def submission_to_run_results(submission: Submission) -> list[RunResult]:
    """Convert a Submission to a list of RunResult for scoring."""
    run_results = []
    for task_result in submission.results:
        for run in task_result.runs:
            run_results.append(
                RunResult(
                    task_id=task_result.task_id,
                    tool=submission.tool.name,
                    run_id=f"submission_{run.run_number}",
                    timestamp=run.timestamp,
                    tool_version=submission.tool.version,
                    model=submission.model.name,
                    outcome=RunOutcome(
                        success=run.outcome.success,
                        partial_credit_score=run.outcome.partial_credit_score,
                        partial_credit_max=run.outcome.partial_credit_max,
                    ),
                    metrics=RunMetrics(
                        wall_clock_seconds=run.metrics.wall_clock_seconds,
                        iteration_count=run.metrics.iteration_count,
                        human_interventions=run.metrics.human_interventions,
                        files_modified=run.metrics.files_modified,
                        lines_changed=run.metrics.lines_changed,
                    ),
                    cost=RunCost(
                        input_tokens=run.cost.input_tokens,
                        output_tokens=run.cost.output_tokens,
                        estimated_cost_usd=run.cost.estimated_cost_usd,
                    ),
                    quality=RunQuality(
                        lint_delta=run.quality.lint_delta,
                        security_delta=run.quality.security_delta,
                        test_regressions=run.quality.test_regressions,
                    ),
                    environment=RunEnvironment(
                        os=submission.environment.os,
                        hardware=submission.environment.hardware_detail,
                    ),
                )
            )
    return run_results


def load_submission(path: Path) -> Submission:
    """Load and validate a submission file."""
    with path.open() as f:
        data = json.load(f)
    errors = validate_submission(data)
    if errors:
        raise ValueError(f"Invalid submission: {'; '.join(errors)}")
    return parse_submission(data)
