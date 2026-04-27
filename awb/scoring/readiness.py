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


def compute_readiness_score(
    *,
    correctness: float,
    regression_safety: float,
    security: float,
    review_burden: float,
    maintainability: float,
    cost: float,
    speed: float,
) -> float:
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
    total = sum(inputs[name] * w for name, w in READINESS_DIMENSIONS)
    return round(total, 1)
