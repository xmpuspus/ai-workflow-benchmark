"""Composite score computation with per-task baselines and difficulty weighting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from awb.core.config import RunResult, TaskDefinition
from awb.scoring.baselines import TaskBaselines
from awb.scoring.normalize import (
    normalize_cost,
    normalize_iterations,
    normalize_partial_credit,
    normalize_quality,
    normalize_regressions,
    normalize_security,
    normalize_speed,
    normalize_success_rate,
)

DIFFICULTY_WEIGHT = {"easy": 1.0, "medium": 1.5, "hard": 2.5}

_weight_cache: dict[str, dict[str, float]] = {}


def load_weight_profile(profile: str = "default") -> dict[str, float]:
    """Load a weight profile from weights.yaml (cached after first read)."""
    if profile in _weight_cache:
        return _weight_cache[profile]
    weights_path = Path(__file__).parent / "weights.yaml"
    with weights_path.open() as f:
        all_profiles = yaml.safe_load(f)
    if profile not in all_profiles:
        raise ValueError(f"Unknown weight profile: {profile}. Available: {list(all_profiles)}")
    weights = all_profiles[profile]
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 0.001:
        raise ValueError(f"Weight profile '{profile}' sums to {weight_sum}, expected 1.0")
    _weight_cache[profile] = weights
    return _weight_cache[profile]


@dataclass
class TaskScore:
    """Normalized scores for a single task run."""

    task_id: str
    difficulty: str
    per_metric: dict[str, float] = field(default_factory=dict)
    composite: float = 0.0

    @property
    def difficulty_weight(self) -> float:
        return DIFFICULTY_WEIGHT.get(self.difficulty, 1.0)


def compute_task_score(
    result: RunResult,
    task: TaskDefinition,
    weights: dict[str, float] | None = None,
) -> TaskScore:
    """Compute normalized scores for a single task run using per-task baselines."""
    if weights is None:
        weights = load_weight_profile()

    baselines = TaskBaselines.from_task(task)
    max_pts = result.outcome.partial_credit_max or 1

    success = 100.0 if result.outcome.success else 0.0
    partial = (result.outcome.partial_credit_score / max_pts) * 100

    # Correctness: 60% binary success + 40% partial credit gradient
    correctness = 0.6 * normalize_success_rate(success) + 0.4 * normalize_partial_credit(partial)

    per_metric = {
        "correctness": round(correctness, 1),
        "cost_efficiency": normalize_cost(
            result.cost.estimated_cost_usd,
            baselines.cost_optimal,
            baselines.cost_baseline,
        ),
        "speed": normalize_speed(
            result.metrics.wall_clock_seconds,
            baselines.speed_optimal,
            baselines.speed_baseline,
        ),
        "code_quality": normalize_quality(result.quality.lint_delta, 1),
        "reliability": normalize_regressions(result.quality.test_regressions, 1),
        "security": normalize_security(result.quality.security_delta, 1),
        "efficiency": normalize_iterations(
            result.metrics.iteration_count,
            baselines.iterations_optimal,
            baselines.iterations_baseline,
        ),
    }

    composite = sum(per_metric.get(k, 0) * w for k, w in weights.items())
    return TaskScore(
        task_id=result.task_id,
        difficulty=task.difficulty,
        per_metric=per_metric,
        composite=round(composite, 1),
    )


def compute_aggregate_score(
    results: list[RunResult],
    tasks: dict[str, TaskDefinition],
    weights: dict[str, float] | None = None,
    stability_weights: dict[str, float] | None = None,
) -> tuple[float, list[TaskScore]]:
    """Compute difficulty-weighted aggregate score across multiple task results.

    Returns (aggregate_score, per_task_scores).
    """
    if weights is None:
        weights = load_weight_profile()

    task_scores = []
    for result in results:
        task = tasks.get(result.task_id)
        if not task:
            continue
        task_scores.append(compute_task_score(result, task, weights))

    if not task_scores:
        return 0.0, []

    def _eff_weight(ts: TaskScore) -> float:
        sw = stability_weights.get(ts.task_id, 1.0) if stability_weights else 1.0
        return ts.difficulty_weight * sw

    total_weight = sum(_eff_weight(ts) for ts in task_scores)
    aggregate = sum(ts.composite * _eff_weight(ts) for ts in task_scores) / total_weight
    return round(aggregate, 1), task_scores


# --- Legacy interface for backward compatibility ---


def compute_composite_score(tool_stats: dict) -> float:
    """Compute weighted composite score from aggregated tool stats (legacy).

    Uses global baselines. Prefer compute_task_score for per-task scoring.
    """
    n = tool_stats["total_tasks"] or 1
    success = normalize_success_rate(tool_stats["success_rate"])
    partial = normalize_partial_credit(tool_stats["avg_score_pct"])
    correctness = 0.6 * success + 0.4 * partial

    scores = {
        "correctness": correctness,
        "cost_efficiency": normalize_cost(tool_stats["avg_cost"]),
        "speed": normalize_speed(tool_stats["avg_time"]),
        "code_quality": normalize_quality(tool_stats["total_lint_delta"], n),
        "reliability": normalize_regressions(tool_stats["total_regressions"], n),
        "security": normalize_security(tool_stats["total_security_delta"], n),
        "efficiency": normalize_iterations(tool_stats["avg_iterations"]),
    }
    weights = load_weight_profile()
    composite = sum(scores.get(k, 0) * w for k, w in weights.items())
    return round(composite, 1)
