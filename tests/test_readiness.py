"""Tests for the Production Readiness Score composite."""

from __future__ import annotations

from awb.scoring.readiness import READINESS_DIMENSIONS, compute_readiness_score


def test_dimensions_sum_to_one():
    total = sum(w for _, w in READINESS_DIMENSIONS)
    assert abs(total - 1.0) < 1e-6


def test_dimensions_cover_seven_names():
    names = [name for name, _ in READINESS_DIMENSIONS]
    assert names == [
        "correctness",
        "regression_safety",
        "security",
        "review_burden",
        "maintainability",
        "cost",
        "speed",
    ]


def test_perfect_inputs_return_100():
    score = compute_readiness_score(
        correctness=100,
        regression_safety=100,
        security=100,
        review_burden=100,
        maintainability=100,
        cost=100,
        speed=100,
    )
    assert score == 100.0


def test_zero_inputs_return_zero():
    score = compute_readiness_score(
        correctness=0,
        regression_safety=0,
        security=0,
        review_burden=0,
        maintainability=0,
        cost=0,
        speed=0,
    )
    assert score == 0.0


def test_correctness_dominates_other_dimensions():
    high_correctness = compute_readiness_score(
        correctness=100,
        regression_safety=50,
        security=50,
        review_burden=50,
        maintainability=50,
        cost=50,
        speed=50,
    )
    low_correctness = compute_readiness_score(
        correctness=0,
        regression_safety=100,
        security=100,
        review_burden=100,
        maintainability=100,
        cost=100,
        speed=100,
    )
    # 100*0.35 + 50*0.65 = 67.5 vs 0*0.35 + 100*0.65 = 65
    assert high_correctness > low_correctness


def test_regression_safety_outweighs_review_burden():
    """Per-weight check: regression_safety (0.20) > review_burden (0.10)."""
    a = compute_readiness_score(
        correctness=50,
        regression_safety=100,
        security=50,
        review_burden=0,
        maintainability=50,
        cost=50,
        speed=50,
    )
    b = compute_readiness_score(
        correctness=50,
        regression_safety=0,
        security=50,
        review_burden=100,
        maintainability=50,
        cost=50,
        speed=50,
    )
    assert a > b
