from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DiffStats:
    files_modified: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    total_changes: int = 0


def analyze_diff(diff_text: str) -> DiffStats:
    """Parse a unified diff and return statistics."""
    stats = DiffStats()
    for line in diff_text.splitlines():
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            stats.files_modified += 1
        elif line.startswith("+") and not line.startswith("+++ "):
            stats.lines_added += 1
        elif line.startswith("-") and not line.startswith("--- "):
            stats.lines_removed += 1
    stats.total_changes = stats.lines_added + stats.lines_removed
    return stats


# Lines-changed thresholds considered "minimal" per difficulty level
_MINIMAL_THRESHOLDS = {
    "easy": 50,
    "medium": 150,
    "hard": 400,
}


def assess_patch_quality(diff_text: str, task_difficulty: str) -> dict[str, Any]:
    stats = analyze_diff(diff_text)
    threshold = _MINIMAL_THRESHOLDS.get(task_difficulty.lower(), 150)
    is_minimal = stats.total_changes <= threshold

    warnings: list[str] = []
    if not is_minimal:
        warnings.append(
            f"large patch for {task_difficulty} task ({stats.total_changes} lines changed)"
        )
    if stats.files_modified == 0 and diff_text.strip():
        warnings.append("diff has content but no recognizable file headers")

    return {
        "is_minimal": is_minimal,
        "stats": stats,
        "warnings": warnings,
    }
