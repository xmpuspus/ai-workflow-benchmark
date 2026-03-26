"""Tests for code review scorer."""

import pytest

from awb.verification.code_review_scorer import ReviewScore, score_code_review


class TestScoreCodeReview:
    @pytest.mark.asyncio
    async def test_perfect_review_finds_all_issues(self, tmp_workspace):
        known_issues = ["null pointer dereference", "sql injection"]
        review = "Found a null pointer dereference on line 10. Also has a sql injection."
        score = await score_code_review(review, known_issues, tmp_workspace)
        assert score.true_positives == 2
        assert score.false_negatives == 0
        assert score.recall == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_empty_review_misses_all_issues(self, tmp_workspace):
        known_issues = ["race condition", "buffer overflow"]
        score = await score_code_review("", known_issues, tmp_workspace)
        assert score.true_positives == 0
        assert score.false_negatives == 2
        assert score.recall == pytest.approx(0.0)
        assert score.f1 == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_no_known_issues_zero_recall_denominator(self, tmp_workspace):
        score = await score_code_review("This code looks fine.", [], tmp_workspace)
        assert score.true_positives == 0
        assert score.false_negatives == 0
        assert score.recall == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_false_positives_counted(self, tmp_workspace):
        # _FINDING_RE matches lines containing: issue, bug, vulnerability, problem
        # Two separate lines, each with a match — neither is the known issue text
        known_issues = ["xss attack"]
        review = "Line 5 has an issue.\nLine 12 has a problem."
        score = await score_code_review(review, known_issues, tmp_workspace)
        assert score.true_positives == 0
        assert score.false_positives == 2

    @pytest.mark.asyncio
    async def test_returns_review_score_dataclass(self, tmp_workspace):
        score = await score_code_review("no issues found", [], tmp_workspace)
        assert isinstance(score, ReviewScore)

    @pytest.mark.asyncio
    async def test_precision_and_recall_balanced(self, tmp_workspace):
        known_issues = ["memory leak"]
        review = "There is a memory leak in the allocator. This is a bug."
        score = await score_code_review(review, known_issues, tmp_workspace)
        assert score.true_positives == 1
        assert 0.0 <= score.precision <= 1.0
        assert score.recall == pytest.approx(1.0)
        assert score.f1 > 0.0

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self, tmp_workspace):
        known_issues = ["NULL POINTER"]
        review = "Found a null pointer dereference."
        score = await score_code_review(review, known_issues, tmp_workspace)
        assert score.true_positives == 1
