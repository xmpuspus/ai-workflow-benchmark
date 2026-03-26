"""Benchmark integrity checks — contamination detection and variance anomalies."""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from awb.core.config import RunResult

MIN_PLAUSIBLE_SECONDS = 10


@dataclass
class IntegrityWarning:
    task_id: str
    category: str  # "contamination" or "variance_anomaly"
    message: str
    severity: str  # "warning" or "critical"

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.task_id}: {self.message}"


def detect_contamination(results: list[RunResult]) -> list[IntegrityWarning]:
    """Flag suspicious patterns suggesting task contamination or pre-cached solutions."""
    warnings = []

    for result in results:
        # Suspiciously fast with success
        if result.metrics.wall_clock_seconds < MIN_PLAUSIBLE_SECONDS and result.outcome.success:
            warnings.append(IntegrityWarning(
                task_id=result.task_id,
                category="contamination",
                message=(
                    f"Completed in {result.metrics.wall_clock_seconds:.1f}s with full success. "
                    f"Possible pre-cached solution."
                ),
                severity="critical",
            ))

        # Zero or one iteration but success
        if result.metrics.iteration_count <= 1 and result.outcome.success:
            warnings.append(IntegrityWarning(
                task_id=result.task_id,
                category="contamination",
                message=(
                    f"Succeeded in {result.metrics.iteration_count} iteration(s). "
                    f"Verify tool actually executed."
                ),
                severity="warning",
            ))

        # No tool calls but success
        if not result.metrics.tool_calls and result.outcome.success:
            warnings.append(IntegrityWarning(
                task_id=result.task_id,
                category="contamination",
                message="No tool calls recorded but task passed. Possible pre-existing solution.",
                severity="critical",
            ))

    return warnings


def detect_variance_anomalies(results: list[RunResult]) -> list[IntegrityWarning]:
    """Flag near-zero variance across runs (suggests deterministic replay)."""
    warnings = []

    by_task: dict[str, list[RunResult]] = defaultdict(list)
    for r in results:
        by_task[r.task_id].append(r)

    for task_id, runs in by_task.items():
        if len(runs) < 3:
            continue

        times = [r.metrics.wall_clock_seconds for r in runs]
        if statistics.stdev(times) < 0.1:
            warnings.append(IntegrityWarning(
                task_id=task_id,
                category="variance_anomaly",
                message=(
                    f"Near-zero variance in wall-clock time across {len(times)} runs "
                    f"(stdev={statistics.stdev(times):.3f}s). "
                    f"LLM outputs should have some variance."
                ),
                severity="warning",
            ))

        # Check token count variance too
        tokens = [r.cost.input_tokens + r.cost.output_tokens for r in runs]
        if all(t > 0 for t in tokens) and len(set(tokens)) == 1:
            warnings.append(IntegrityWarning(
                task_id=task_id,
                category="variance_anomaly",
                message=(
                    f"Identical token counts across {len(runs)} runs ({tokens[0]} tokens each). "
                    f"Suggests cached/replayed responses."
                ),
                severity="critical",
            ))

    return warnings


def run_integrity_checks(results: list[RunResult]) -> list[IntegrityWarning]:
    """Run all integrity checks and return combined warnings."""
    warnings = detect_contamination(results)
    warnings.extend(detect_variance_anomalies(results))
    return sorted(warnings, key=lambda w: (w.severity == "warning", w.task_id))
