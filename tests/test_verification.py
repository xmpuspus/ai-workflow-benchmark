"""Tests for verification modules."""

import tempfile
from pathlib import Path

import pytest

from awb.core.config import PartialCreditCriterion
from awb.verification.diff_analyzer import DiffStats, analyze_diff, assess_patch_quality
from awb.verification.partial_credit import evaluate_partial_credit

SAMPLE_DIFF = """diff --git a/foo.py b/foo.py
index 1234567..abcdefg 100644
--- a/foo.py
+++ b/foo.py
@@ -1,5 +1,7 @@
 import os
+import threading

 class Session:
-    data = {}
+    _lock = threading.Lock()
+    data = {}

     def get(self, key):
"""


class TestDiffAnalyzer:
    def test_analyze_basic_diff(self):
        stats = analyze_diff(SAMPLE_DIFF)
        assert isinstance(stats, DiffStats)
        assert stats.files_modified == 1
        assert stats.lines_added >= 2
        assert stats.lines_removed >= 1
        assert stats.total_changes == stats.lines_added + stats.lines_removed

    def test_empty_diff(self):
        stats = analyze_diff("")
        assert stats.files_modified == 0
        assert stats.total_changes == 0

    def test_patch_quality_easy_task(self):
        result = assess_patch_quality(SAMPLE_DIFF, "easy")
        assert "is_minimal" in result
        assert "stats" in result
        assert "warnings" in result


class TestPartialCredit:
    @pytest.mark.asyncio
    async def test_passing_criterion(self):
        criteria = [
            PartialCreditCriterion(criterion="Always passes", points=50, check="true"),
        ]
        with tempfile.TemporaryDirectory() as d:
            earned, max_pts, breakdown = await evaluate_partial_credit(criteria, Path(d))
        assert earned == 50
        assert max_pts == 50
        assert len(breakdown) == 1
        assert breakdown[0].passed is True

    @pytest.mark.asyncio
    async def test_failing_criterion(self):
        criteria = [
            PartialCreditCriterion(criterion="Always fails", points=30, check="false"),
        ]
        with tempfile.TemporaryDirectory() as d:
            earned, max_pts, breakdown = await evaluate_partial_credit(criteria, Path(d))
        assert earned == 0
        assert max_pts == 30
        assert breakdown[0].passed is False

    @pytest.mark.asyncio
    async def test_mixed_criteria(self):
        criteria = [
            PartialCreditCriterion(criterion="Pass", points=60, check="true"),
            PartialCreditCriterion(criterion="Fail", points=40, check="false"),
        ]
        with tempfile.TemporaryDirectory() as d:
            earned, max_pts, breakdown = await evaluate_partial_credit(criteria, Path(d))
        assert earned == 60
        assert max_pts == 100
