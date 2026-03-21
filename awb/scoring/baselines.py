"""Per-task scoring baselines derived from task difficulty and constraints."""
from __future__ import annotations

from dataclasses import dataclass

from awb.core.config import TaskDefinition

# Optimal = ~95 score, Baseline = ~50 score
_DIFFICULTY_COST = {
    "easy": (0.05, 0.30),
    "medium": (0.20, 1.00),
    "hard": (1.00, 3.00),
}

_DIFFICULTY_ITERATIONS_OPTIMAL = {
    "easy": 3,
    "medium": 8,
    "hard": 15,
}


@dataclass
class TaskBaselines:
    """Scoring baselines for a single task.

    optimal = excellent performance (~95 normalized score)
    baseline = adequate performance (~50 normalized score)
    """

    speed_optimal: float
    speed_baseline: float
    cost_optimal: float
    cost_baseline: float
    iterations_optimal: int
    iterations_baseline: int

    @classmethod
    def from_task(cls, task: TaskDefinition) -> TaskBaselines:
        cost_opt, cost_base = _DIFFICULTY_COST.get(task.difficulty, (0.20, 1.00))
        iter_opt = _DIFFICULTY_ITERATIONS_OPTIMAL.get(task.difficulty, 8)
        return cls(
            speed_optimal=task.estimated_minutes * 30,  # 50% of estimated
            speed_baseline=task.estimated_minutes * 60,  # 100% of estimated
            cost_optimal=cost_opt,
            cost_baseline=cost_base,
            iterations_optimal=iter_opt,
            iterations_baseline=task.constraints.max_iterations,
        )
