"""Fast-check task selection — picks representative tasks for quick benchmarking."""

from __future__ import annotations

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


def estimate_full_score(
    fast_results: list[dict],
    total_tasks: int = 100,
) -> tuple[float, float]:
    """Estimate full-suite score from fast-check results.

    Returns (estimated_score, confidence_margin).
    """
    if not fast_results:
        return 0.0, 0.0

    scores = []
    for r in fast_results:
        max_pts = r.get("partial_credit_max", 1) or 1
        pct = (r.get("partial_credit_score", 0) / max_pts) * 100
        scores.append(pct)

    mean = sum(scores) / len(scores)
    if len(scores) > 1:
        variance = sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)
        std_dev = variance**0.5
        # 95% CI margin: t-value ~2.4 for n=8
        margin = 2.4 * std_dev / (len(scores) ** 0.5)
    else:
        margin = 25.0  # High uncertainty with single sample

    return round(mean, 1), round(margin, 1)
