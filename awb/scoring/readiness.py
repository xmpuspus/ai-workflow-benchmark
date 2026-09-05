"""Production Readiness Score — composite over 7 shipping dimensions.

Designed to answer: "can this AI workflow safely ship real software?"
Correctness dominates, then regression-safety + security, then the
operational dimensions (review burden, maintainability, cost, speed).
"""

from __future__ import annotations

# Weights sum to 1.0. Order is deliberate: the dimensions on top are the
# ones that decide whether code can ship without a human catching a bug.
READINESS_DIMENSIONS: list[tuple[str, float]] = [
    ("correctness", 0.35),
    ("regression_safety", 0.20),
    ("security", 0.15),
    ("review_burden", 0.10),
    ("maintainability", 0.08),
    ("cost", 0.07),
    ("speed", 0.05),
]


# Heuristic mapping from raw RunResult fields onto the 0-100 readiness dims.
# Single source of truth: leaderboard_cmd re-exports these for tunability.
REVIEW_BURDEN_FILES_TO_ZERO = 50.0  # ~50 modified files -> ~0 review-burden score
MAINTAINABILITY_LINT_TO_ZERO = 20.0  # 20+ new lint warnings -> ~0 maintainability
COST_USD_TO_ZERO = 5.0  # $5 per task -> ~0 cost score
SPEED_SECONDS_TO_ZERO = 1800.0  # 30 min -> ~0 speed score


def compute_readiness_score(
    *,
    correctness: float,
    regression_safety: float | None,
    security: float | None,
    review_burden: float,
    maintainability: float,
    cost: float,
    speed: float,
) -> float | None:
    """Weighted composite over 7 dimensions, each expressed as 0-100."""
    inputs = {
        "correctness": correctness,
        "regression_safety": regression_safety,
        "security": security,
        "review_burden": review_burden,
        "maintainability": maintainability,
        "cost": cost,
        "speed": speed,
    }
    if any(inputs[name] is None for name, _ in READINESS_DIMENSIONS):
        return None
    total = sum(inputs[name] * w for name, w in READINESS_DIMENSIONS)  # type: ignore[operator]
    return round(total, 1)


def quality_measurement_status(result, field: str) -> str:
    quality = result.quality
    direct = getattr(quality, f"{field}_status", None)
    if direct:
        return str(direct)
    for container_name in ("measurement_status", "evidence_status"):
        container = getattr(result, container_name, None)
        if isinstance(container, dict) and container.get(field):
            return str(container[field])
    return "missing"


def _measured_quality_values(results: list, field: str) -> tuple[list[float], dict]:
    values = []
    statuses: dict[str, int] = {}
    for result in results:
        status = quality_measurement_status(result, field)
        statuses[status] = statuses.get(status, 0) + 1
        if status not in {"measured", "measured_clean", "measured_findings"}:
            continue
        if field == "security":
            raw = result.quality.security_delta
        else:
            raw = result.quality.test_regressions
        values.append(100.0 if raw <= 0 else 0.0)
    return values, {"measured": len(values), "total": len(results), "statuses": statuses}


def readiness_from_results(results: list) -> dict:
    """Derive the 7 readiness dimensions + composite from a list of RunResults.

    Shared by the leaderboard (`--readiness`) and the baseline export so both
    compute the score identically. Returns a dict with the 7 dims, `composite`,
    and `n_results`.
    """
    n = len(results) or 1

    def _mean(fn):
        return sum(fn(r) for r in results) / n

    correctness = 100.0 * sum(1 for r in results if r.outcome.success) / n
    regression_values, regression_coverage = _measured_quality_values(results, "test_regressions")
    security_values, security_coverage = _measured_quality_values(results, "security")
    regression_safety = (
        sum(regression_values) / len(regression_values)
        if len(regression_values) == len(results) and results
        else None
    )
    security = (
        sum(security_values) / len(security_values)
        if len(security_values) == len(results) and results
        else None
    )
    review_burden = max(
        0.0, 100.0 - 100.0 * _mean(lambda r: r.metrics.files_modified) / REVIEW_BURDEN_FILES_TO_ZERO
    )
    maintainability = max(
        0.0,
        100.0
        - 100.0 * max(0.0, _mean(lambda r: r.quality.lint_delta)) / MAINTAINABILITY_LINT_TO_ZERO,
    )
    cost = max(0.0, 100.0 - 100.0 * _mean(lambda r: r.cost.estimated_cost_usd) / COST_USD_TO_ZERO)
    speed = max(
        0.0, 100.0 - 100.0 * _mean(lambda r: r.metrics.wall_clock_seconds) / SPEED_SECONDS_TO_ZERO
    )
    composite = compute_readiness_score(
        correctness=correctness,
        regression_safety=regression_safety,
        security=security,
        review_burden=review_burden,
        maintainability=maintainability,
        cost=cost,
        speed=speed,
    )
    return {
        "composite": composite,
        "correctness": round(correctness, 1),
        "regression_safety": round(regression_safety, 1) if regression_safety is not None else None,
        "security": round(security, 1) if security is not None else None,
        "review_burden": round(review_burden, 1),
        "maintainability": round(maintainability, 1),
        "cost": round(cost, 1),
        "speed": round(speed, 1),
        "n_results": len(results),
        "coverage": {
            "regression_safety": regression_coverage,
            "security": security_coverage,
        },
    }
