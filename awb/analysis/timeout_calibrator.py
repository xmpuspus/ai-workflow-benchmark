"""Calibrate task timeouts using empirical wall clock data."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from awb.core.config import RunResult


@dataclass
class TimeoutRecommendation:
    task_id: str
    current_timeout: int
    p95_time: float
    recommended_timeout: int
    changed: bool


def calibrate_timeouts(
    results: list[RunResult],
    multiplier: float = 2.5,
    min_timeout: int = 120,
) -> list[TimeoutRecommendation]:
    """Compute p95 wall clock per task, recommend ceil(p95 * multiplier)."""
    from awb.core.task_loader import load_all_tasks

    task_map = {t.id: t for t in load_all_tasks()}

    by_task: dict[str, list[float]] = {}
    for r in results:
        by_task.setdefault(r.task_id, []).append(r.metrics.wall_clock_seconds)

    recs = []
    for tid, times in sorted(by_task.items()):
        times_sorted = sorted(times)
        idx = int(math.ceil(len(times_sorted) * 0.95)) - 1
        p95 = times_sorted[max(0, idx)]

        current = task_map[tid].constraints.timeout_seconds if tid in task_map else 1800
        recommended = max(min_timeout, min(current, math.ceil(p95 * multiplier)))
        recs.append(
            TimeoutRecommendation(
                task_id=tid,
                current_timeout=current,
                p95_time=round(p95, 1),
                recommended_timeout=recommended,
                changed=recommended != current,
            )
        )

    return sorted(recs, key=lambda r: -r.current_timeout)


def apply_timeouts(
    recommendations: list[TimeoutRecommendation],
    tasks_dir: Path,
) -> int:
    """Update timeout_seconds field in task YAML files. Returns count changed."""
    changed = 0
    for rec in recommendations:
        if not rec.changed:
            continue
        matches = list(tasks_dir.rglob(f"{rec.task_id}.yaml"))
        if not matches:
            continue
        path = matches[0]
        content = path.read_text()
        new_content = re.sub(
            r"^(\s*timeout_seconds:\s*)\d+",
            rf"\g<1>{rec.recommended_timeout}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if new_content != content:
            path.write_text(new_content)
            changed += 1
    return changed
