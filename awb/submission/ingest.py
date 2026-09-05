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
    eligibility_raw = sub.get("comparison_eligibility", {})
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
                        estimated_credits=cost_raw.get("estimated_credits"),
                        usage_status=cost_raw.get("usage_status", "unknown"),
                    ),
                    quality=SubmissionRunQuality(
                        lint_delta=quality_raw.get("lint_delta", 0),
                        security_delta=quality_raw.get("security_delta", 0),
                        test_regressions=quality_raw.get("test_regressions", 0),
                        security_status=quality_raw.get("security_status", "missing"),
                        test_regressions_status=quality_raw.get(
                            "test_regressions_status", "missing"
                        ),
                        lint_status=quality_raw.get("lint_status", "missing"),
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
        comparison_eligible=eligibility_raw.get("eligible", False),
        ineligibility_reasons=eligibility_raw.get("reasons", ["legacy export lacks identity"]),
        comparison_identity=eligibility_raw.get("identity", {}),
    )


def submission_to_run_results(submission: Submission) -> list[RunResult]:
    """Convert a Submission to a list of RunResult for scoring."""
    run_results = []
    for task_result in submission.results:
        for run in task_result.runs:
            result = RunResult(
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
                    estimated_credits=run.cost.estimated_credits,
                    usage_status=run.cost.usage_status,
                ),
                quality=RunQuality(
                    lint_delta=run.quality.lint_delta,
                    security_delta=run.quality.security_delta,
                    test_regressions=run.quality.test_regressions,
                    lint_status=run.quality.lint_status,
                    security_status=run.quality.security_status,
                    test_regressions_status=run.quality.test_regressions_status,
                ),
                environment=RunEnvironment(
                    os=submission.environment.os,
                    hardware=submission.environment.hardware_detail,
                ),
                task_set_hash=submission.task_set_hash,
            )
            for field_name, value in submission.comparison_identity.items():
                if value:
                    setattr(result, field_name, value)
            run_results.append(result)
    return run_results


def load_submission(path: Path) -> Submission:
    """Load and validate a submission file."""
    with path.open() as f:
        data = json.load(f)
    errors = validate_submission(data)
    if errors:
        raise ValueError(f"Invalid submission: {'; '.join(errors)}")
    return parse_submission(data)
