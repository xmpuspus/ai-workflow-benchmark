"""Fast-check task selection — picks representative tasks for quick benchmarking."""

from __future__ import annotations

from dataclasses import dataclass

from awb.core.config import TaskDefinition

# Hand-picked representative task IDs: 1 per category, prefer easy/medium, stable tasks
_REPRESENTATIVE_TASKS = {
    "bug-fix": "BF-001",
    "code-review": "CR-001",
    "debugging": "DB-001",
    "feature-addition": "FA-001",
    "legacy-code": "LC-001",
    "multi-file": "MF-001",
    "refactoring": "RF-001",
    "workflow": "WF-001",
}


def select_fast_check_tasks(all_tasks: list[TaskDefinition]) -> list[TaskDefinition]:
    """Select representative tasks for fast-check mode.

    Returns 1 task per category (8 total). Uses hand-picked IDs that are
    stable, representative, and relatively quick to execute.
    """
    task_map = {t.id: t for t in all_tasks}
    selected = []

    for category, task_id in sorted(_REPRESENTATIVE_TASKS.items()):
        if task_id in task_map:
            selected.append(task_map[task_id])
        else:
            # Fallback: pick first task in category
            for t in all_tasks:
                if t.category == category:
                    selected.append(t)
                    break

    return selected


@dataclass(frozen=True)
class FastCheckSummary:
    sample_mean: float | None
    sample_min: float | None
    sample_max: float | None
    n_tasks: int
    design: str = "exploratory_hand_picked"
    population_inference: bool = False
    message: str = (
        "Exploratory result for the selected fast-check tasks; "
        "it does not estimate full-suite performance."
    )


def summarize_fast_check(fast_results: list[dict]) -> FastCheckSummary:
    """Describe the fixed fast-check sample without population inference."""
    if not fast_results:
        return FastCheckSummary(sample_mean=None, sample_min=None, sample_max=None, n_tasks=0)

    scores = []
    for r in fast_results:
        max_pts = r.get("partial_credit_max", 1) or 1
        pct = (r.get("partial_credit_score", 0) / max_pts) * 100
        scores.append(pct)

    return FastCheckSummary(
        sample_mean=round(sum(scores) / len(scores), 1),
        sample_min=round(min(scores), 1),
        sample_max=round(max(scores), 1),
        n_tasks=len(scores),
    )


def estimate_full_score(fast_results: list[dict], total_tasks: int = 100) -> tuple[float, float]:
    """Compatibility wrapper returning the selected-sample mean and no margin.

    The second value is always zero because this fixed, hand-picked sample
    does not support an inferential margin for ``total_tasks``.
    """
    del total_tasks
    summary = summarize_fast_check(fast_results)
    return summary.sample_mean or 0.0, 0.0
