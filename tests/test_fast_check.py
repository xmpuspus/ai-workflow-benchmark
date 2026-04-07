"""Tests for fast-check task selection and score estimation."""

from awb.core.fast_check import estimate_full_score, select_fast_check_tasks


class TestSelectFastCheckTasks:
    def test_selects_one_per_category(self, sample_task):
        tasks = [sample_task]
        selected = select_fast_check_tasks(tasks)
        assert len(selected) >= 1

    def test_returns_up_to_eight_tasks(self):
        from awb.core.task_loader import load_all_tasks

        all_tasks = load_all_tasks()
        selected = select_fast_check_tasks(all_tasks)
        assert len(selected) <= 8
        assert len(selected) >= 1

    def test_covers_multiple_categories(self):
        from awb.core.task_loader import load_all_tasks

        all_tasks = load_all_tasks()
        selected = select_fast_check_tasks(all_tasks)
        categories = {t.category for t in selected}
        assert len(categories) >= 2


class TestEstimateFullScore:
    def test_perfect_scores(self):
        results = [
            {"partial_credit_score": 100, "partial_credit_max": 100}
            for _ in range(8)
        ]
        est, margin = estimate_full_score(results)
        assert est == 100.0
        assert margin == 0.0

    def test_zero_scores(self):
        results = [
            {"partial_credit_score": 0, "partial_credit_max": 100}
            for _ in range(8)
        ]
        est, margin = estimate_full_score(results)
        assert est == 0.0

    def test_mixed_scores(self):
        results = [
            {"partial_credit_score": 80, "partial_credit_max": 100},
            {"partial_credit_score": 60, "partial_credit_max": 100},
            {"partial_credit_score": 40, "partial_credit_max": 100},
        ]
        est, margin = estimate_full_score(results)
        assert 50 < est < 70
        assert margin > 0

    def test_empty_results(self):
        est, margin = estimate_full_score([])
        assert est == 0.0
        assert margin == 0.0

    def test_single_result_high_uncertainty(self):
        results = [{"partial_credit_score": 50, "partial_credit_max": 100}]
        _, margin = estimate_full_score(results)
        assert margin == 25.0  # High uncertainty for single sample
