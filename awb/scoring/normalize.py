"""Normalization functions mapping raw metrics to [0, 100] scores.

Uses sigmoid-based normalization that:
- Maps optimal value to ~95, baseline value to ~50
- Never produces negative scores
- Provides smooth gradient at all values (no cliffs)
"""
from __future__ import annotations

import math


def sigmoid_normalize(
    value: float,
    optimal: float,
    baseline: float,
    lower_is_better: bool = True,
) -> float:
    """Map a raw metric value to [0, 100] using a sigmoid curve.

    Args:
        value: Raw metric value.
        optimal: Value that should score ~95 (excellent).
        baseline: Value that should score ~50 (adequate).
        lower_is_better: True for cost, speed, iterations. False for success rate.

    Returns:
        Normalized score in [0, 100].
    """
    if abs(baseline - optimal) < 1e-9:
        if lower_is_better:
            return 100.0 if value <= optimal else 0.0
        return 100.0 if value >= optimal else 0.0

    # k controls steepness: maps baseline->50, optimal->~95
    # Sigmoid center is at baseline (score=50), optimal scores ~95
    k = math.log(19) / abs(baseline - optimal)

    x = k * (value - baseline) if lower_is_better else k * (baseline - value)

    # Clamp exponent to prevent overflow
    x = max(-50, min(50, x))
    score = 100.0 / (1.0 + math.exp(x))
    return round(max(0.0, min(100.0, score)), 1)


# --- Convenience wrappers for backward compatibility ---
# These use global defaults when per-task baselines are not provided.

def normalize_success_rate(rate: float) -> float:
    """Passthrough clamped to [0, 100]."""
    return round(max(0.0, min(100.0, rate)), 1)


def normalize_partial_credit(avg_score_pct: float) -> float:
    """Passthrough clamped to [0, 100]."""
    return round(max(0.0, min(100.0, avg_score_pct)), 1)


def normalize_cost(avg_cost: float, optimal: float = 0.05, baseline: float = 1.0) -> float:
    return sigmoid_normalize(avg_cost, optimal, baseline, lower_is_better=True)


def normalize_quality(total_lint_delta: int, total_tasks: int) -> float:
    avg_delta = abs(total_lint_delta) / max(total_tasks, 1)
    return sigmoid_normalize(avg_delta, 0.0, 5.0, lower_is_better=True)


def normalize_speed(avg_time: float, optimal: float = 60.0, baseline: float = 600.0) -> float:
    return sigmoid_normalize(avg_time, optimal, baseline, lower_is_better=True)


def normalize_regressions(total_regressions: int, total_tasks: int) -> float:
    avg_regressions = total_regressions / max(total_tasks, 1)
    return sigmoid_normalize(avg_regressions, 0.0, 2.0, lower_is_better=True)


def normalize_security(total_security_delta: int, total_tasks: int) -> float:
    avg_delta = abs(total_security_delta) / max(total_tasks, 1)
    return sigmoid_normalize(avg_delta, 0.0, 3.0, lower_is_better=True)


def normalize_iterations(
    avg_iterations: float, optimal: float = 3.0, baseline: float = 20.0,
) -> float:
    return sigmoid_normalize(avg_iterations, optimal, baseline, lower_is_better=True)
