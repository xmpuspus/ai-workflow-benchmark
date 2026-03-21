"""Statistical framework — confidence intervals, significance testing, variance reporting."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

# t-distribution critical values for two-tailed 95% CI
_T_CRIT_95 = {
    2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
    7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262, 15: 2.131,
    20: 2.086, 30: 2.042, 50: 2.009, 100: 1.984,
}


@dataclass
class ScoredMetric:
    """A metric with statistical context."""
    value: float
    ci_lower: float
    ci_upper: float
    std_dev: float
    n_runs: int
    sufficient: bool  # True if n_runs meets recommended minimum

    def to_dict(self) -> dict:
        return {
            "value": round(self.value, 1),
            "ci_lower": round(self.ci_lower, 1),
            "ci_upper": round(self.ci_upper, 1),
            "std_dev": round(self.std_dev, 1),
            "n_runs": self.n_runs,
            "sufficient": self.sufficient,
        }


def _t_critical(n: int) -> float:
    """Get t critical value for n observations, 95% confidence."""
    if n in _T_CRIT_95:
        return _T_CRIT_95[n]
    # Interpolate or use z for large n
    if n > 100:
        return 1.96
    # Find closest
    keys = sorted(_T_CRIT_95.keys())
    for i, k in enumerate(keys):
        if k >= n:
            if i == 0:
                return _T_CRIT_95[k]
            prev = keys[i - 1]
            # Linear interpolation
            frac = (n - prev) / (k - prev)
            return _T_CRIT_95[prev] + frac * (_T_CRIT_95[k] - _T_CRIT_95[prev])
    return 1.96


def t_ci(values: list[float], confidence: float = 0.95) -> tuple[float, float, float]:
    """Compute (mean, ci_lower, ci_upper) using t-distribution. Stdlib only."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    if n == 1:
        v = values[0]
        return v, v, v

    mean = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(n)
    t = _t_critical(n)
    margin = t * se
    return mean, mean - margin, mean + margin


def scored_metric(values: list[float], min_runs: int = 3) -> ScoredMetric:
    """Build a ScoredMetric from a list of raw values."""
    n = len(values)
    if n == 0:
        return ScoredMetric(0.0, 0.0, 0.0, 0.0, 0, False)

    mean, ci_lo, ci_hi = t_ci(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    return ScoredMetric(
        value=round(mean, 1),
        ci_lower=round(ci_lo, 1),
        ci_upper=round(ci_hi, 1),
        std_dev=round(sd, 1),
        n_runs=n,
        sufficient=n >= min_runs,
    )


def runs_sufficient(values: list[float], margin: float = 5.0) -> bool:
    """Check if n runs gives a CI width within +/- margin points."""
    if len(values) < 2:
        return False
    _, lo, hi = t_ci(values)
    half_width = (hi - lo) / 2
    return half_width <= margin


@dataclass
class ComparisonResult:
    """Result of comparing two tools on shared tasks."""
    significant: bool
    p_value: float | None
    effect_size: float  # Cohen's d
    effect_interpretation: str
    mean_difference: float
    n_tasks: int
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "significant": self.significant,
            "p_value": self.p_value,
            "effect_size": round(self.effect_size, 2),
            "effect_interpretation": self.effect_interpretation,
            "mean_difference": round(self.mean_difference, 1),
            "n_tasks": self.n_tasks,
            "message": self.message,
        }


def _interpret_effect(d: float) -> str:
    """Interpret Cohen's d effect size."""
    d = abs(d)
    if d < 0.2:
        return "negligible"
    if d < 0.5:
        return "small"
    if d < 0.8:
        return "medium"
    return "large"


def compare_tools_paired(
    scores_a: list[float],
    scores_b: list[float],
) -> ComparisonResult:
    """Compare two tools using sign test (no scipy needed).

    Uses a simple sign test: count how many tasks A beats B vs B beats A.
    Under null hypothesis (no difference), this follows a binomial distribution.
    """
    if len(scores_a) != len(scores_b):
        return ComparisonResult(
            significant=False, p_value=None, effect_size=0.0,
            effect_interpretation="n/a", mean_difference=0.0,
            n_tasks=0, message="Score lists must have equal length",
        )

    n = len(scores_a)
    if n < 5:
        return ComparisonResult(
            significant=False, p_value=None, effect_size=0.0,
            effect_interpretation="n/a", mean_difference=0.0,
            n_tasks=n, message="Need 5+ common tasks for significance testing",
        )

    diffs = [a - b for a, b in zip(scores_a, scores_b, strict=True)]
    non_zero = [d for d in diffs if abs(d) > 0.01]
    n_nz = len(non_zero)

    if n_nz == 0:
        return ComparisonResult(
            significant=False, p_value=1.0, effect_size=0.0,
            effect_interpretation="negligible", mean_difference=0.0,
            n_tasks=n, message="Tools scored identically on all tasks",
        )

    # Sign test: count positives
    n_pos = sum(1 for d in non_zero if d > 0)
    # Two-tailed p-value using binomial CDF approximation
    p_value = _binomial_two_tailed_p(n_pos, n_nz)

    # Cohen's d
    mean_diff = statistics.mean(diffs)
    sd_diff = statistics.stdev(diffs) if len(diffs) > 1 else 1.0
    cohens_d = mean_diff / sd_diff if sd_diff > 0 else 0.0

    direction = "A" if mean_diff > 0 else "B"
    return ComparisonResult(
        significant=p_value < 0.05,
        p_value=round(p_value, 4),
        effect_size=round(cohens_d, 2),
        effect_interpretation=_interpret_effect(cohens_d),
        mean_difference=round(mean_diff, 1),
        n_tasks=n,
        message=f"Tool {direction} scores higher. Effect: {_interpret_effect(cohens_d)}.",
    )


def _binomial_two_tailed_p(k: int, n: int) -> float:
    """Two-tailed p-value for sign test using exact binomial (small n).

    P(X >= k) + P(X <= n-k) under B(n, 0.5).
    """
    if n > 30:
        # Normal approximation
        z = abs(2 * k - n) / math.sqrt(n)
        # Approximate standard normal CDF
        p = math.erfc(z / math.sqrt(2))
        return min(1.0, p)

    # Exact: sum binomial probabilities
    def _binom_pmf(x: int, nn: int) -> float:
        return math.comb(nn, x) * (0.5 ** nn)

    tail = min(k, n - k)
    p = sum(_binom_pmf(i, n) for i in range(tail + 1))
    return min(1.0, 2 * p)  # Two-tailed
