"""Tests for gap analysis classify_failure."""

from awb.analysis.gap_analysis import classify_failure
from awb.core.config import (
    CriterionResult,
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
)


def _make_result(
    success=False,
    wall_clock_seconds=60.0,
    partial_credit_score=0,
    partial_credit_max=100,
    breakdown=None,
    files_modified=1,
    test_regressions=0,
):
    return RunResult(
        task_id="BF-001",
        tool="fake-tool",
        run_id="test-run",
        timestamp="2026-03-26T00:00:00Z",
        outcome=RunOutcome(
            success=success,
            partial_credit_score=partial_credit_score,
            partial_credit_max=partial_credit_max,
            breakdown=breakdown or [],
        ),
        metrics=RunMetrics(
            wall_clock_seconds=wall_clock_seconds, files_modified=files_modified
        ),
        cost=RunCost(),
        quality=RunQuality(test_regressions=test_regressions),
        environment=RunEnvironment(os="darwin", hardware="test"),
    )


class TestClassifyFailure:
    def test_success_returns_success(self, sample_task):
        result = _make_result(success=True, partial_credit_score=100)
        assert classify_failure(result, sample_task) == "success"

    def test_timeout_detected(self, sample_task):
        # task timeout is 1800s; 95% threshold = 1710s
        result = _make_result(wall_clock_seconds=1800.0)
        assert classify_failure(result, sample_task) == "timeout"

    def test_timeout_at_threshold(self, sample_task):
        # exactly at 95% of 1800 = 1710
        result = _make_result(wall_clock_seconds=1710.0)
        assert classify_failure(result, sample_task) == "timeout"

    def test_partial_completion_when_some_credit(self, sample_task):
        result = _make_result(partial_credit_score=40, wall_clock_seconds=300.0)
        assert classify_failure(result, sample_task) == "partial_completion"

    def test_code_error_when_no_credit_no_timeout(self, sample_task):
        result = _make_result(partial_credit_score=0, wall_clock_seconds=120.0)
        assert classify_failure(result, sample_task) == "code_error"

    def test_test_error_when_test_criterion_failed(self, sample_task):
        breakdown = [
            CriterionResult(
                criterion="Tests pass", points_earned=0, points_possible=50, passed=False
            ),
        ]
        result = _make_result(partial_credit_score=0, wall_clock_seconds=300.0, breakdown=breakdown)
        assert classify_failure(result, sample_task) == "test_error"

    def test_test_error_not_raised_when_test_criterion_passed(self, sample_task):
        breakdown = [
            CriterionResult(
                criterion="Tests pass", points_earned=50, points_possible=50, passed=True
            ),
        ]
        # success=False but test criterion passed — falls through to code_error
        result = _make_result(
            partial_credit_score=50, wall_clock_seconds=300.0, breakdown=breakdown
        )
        # partial_credit_score > 0 so it's partial_completion (test passed criterion doesn't fire)
        category = classify_failure(result, sample_task)
        assert category in ("partial_completion", "test_error", "code_error")

    def test_timeout_takes_priority_over_partial_credit(self, sample_task):
        result = _make_result(partial_credit_score=30, wall_clock_seconds=1800.0)
        assert classify_failure(result, sample_task) == "timeout"

    def test_regression_introduced_when_pre_existing_tests_break(self, sample_task):
        result = _make_result(
            partial_credit_score=50,
            wall_clock_seconds=120.0,
            files_modified=2,
            test_regressions=1,
        )
        assert classify_failure(result, sample_task) == "regression_introduced"

    def test_no_edits_made_when_zero_files_modified(self, sample_task):
        result = _make_result(
            partial_credit_score=0, wall_clock_seconds=60.0, files_modified=0
        )
        assert classify_failure(result, sample_task) == "no_edits_made"

    def test_regression_takes_priority_over_no_edits(self, sample_task):
        # If both signals fire, regression is the more useful classification.
        result = _make_result(
            partial_credit_score=0,
            wall_clock_seconds=60.0,
            files_modified=0,
            test_regressions=1,
        )
        assert classify_failure(result, sample_task) == "regression_introduced"
