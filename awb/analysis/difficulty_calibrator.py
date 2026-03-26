"""Recalibrate task difficulty labels using empirical pass rates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from awb.core.config import RunResult


@dataclass
class DifficultyRecommendation:
    task_id: str
    current: str
    recommended: str
    pass_rate: float
    n_runs: int
    changed: bool


def calibrate_difficulty(
    results: list[RunResult],
    thresholds: tuple[float, float] = (35.0, 65.0),
) -> list[DifficultyRecommendation]:
    """Compute per-task pass rate and recommend difficulty labels.

    Thresholds: (hard_medium_boundary, medium_easy_boundary)
    <35% pass rate -> hard, 35-65% -> medium, >65% -> easy
    """
    from awb.core.task_loader import load_all_tasks

    task_map = {t.id: t for t in load_all_tasks()}

    by_task: dict[str, list[bool]] = {}
    for r in results:
        by_task.setdefault(r.task_id, []).append(r.outcome.success)

    recs = []
    for tid, outcomes in sorted(by_task.items()):
        n = len(outcomes)
        rate = sum(outcomes) / n * 100
        hard_boundary, easy_boundary = thresholds

        if rate < hard_boundary:
            recommended = "hard"
        elif rate > easy_boundary:
            recommended = "easy"
        else:
            recommended = "medium"

        current = task_map[tid].difficulty if tid in task_map else "unknown"
        recs.append(
            DifficultyRecommendation(
                task_id=tid,
                current=current,
                recommended=recommended,
                pass_rate=round(rate, 1),
                n_runs=n,
                changed=current != recommended,
            )
        )

    return sorted(recs, key=lambda r: r.pass_rate)


def apply_difficulty_labels(
    recommendations: list[DifficultyRecommendation],
    tasks_dir: Path,
) -> int:
    """Update difficulty field in task YAML files. Returns count changed."""
    changed = 0
    for rec in recommendations:
        if not rec.changed:
            continue
        # Find the YAML file
        matches = list(tasks_dir.rglob(f"{rec.task_id}.yaml"))
        if not matches:
            continue
        path = matches[0]
        content = path.read_text()
        new_content = re.sub(
            r"^(difficulty:\s*)\w+",
            rf"\g<1>{rec.recommended}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if new_content != content:
            path.write_text(new_content)
            changed += 1
    return changed
