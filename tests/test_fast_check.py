"""Tests for fast-check task selection and score estimation."""

from awb.core.fast_check import select_fast_check_tasks, summarize_fast_check


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


class TestSummarizeFastCheck:
    def test_perfect_scores(self):
        results = [{"partial_credit_score": 100, "partial_credit_max": 100} for _ in range(8)]
        summary = summarize_fast_check(results)
        assert summary.sample_mean == 100.0
        assert summary.sample_min == 100.0
        assert summary.sample_max == 100.0
        assert summary.population_inference is False

    def test_zero_scores(self):
        results = [{"partial_credit_score": 0, "partial_credit_max": 100} for _ in range(8)]
        summary = summarize_fast_check(results)
        assert summary.sample_mean == 0.0

    def test_mixed_scores(self):
        results = [
            {"partial_credit_score": 80, "partial_credit_max": 100},
            {"partial_credit_score": 60, "partial_credit_max": 100},
            {"partial_credit_score": 40, "partial_credit_max": 100},
        ]
        summary = summarize_fast_check(results)
        assert summary.sample_mean == 60.0
        assert summary.sample_min == 40.0
        assert summary.sample_max == 80.0
        assert summary.design == "exploratory_hand_picked"

    def test_empty_results(self):
        summary = summarize_fast_check([])
        assert summary.sample_mean is None
        assert summary.n_tasks == 0

    def test_single_result_stays_descriptive(self):
        results = [{"partial_credit_score": 50, "partial_credit_max": 100}]
        summary = summarize_fast_check(results)
        assert summary.sample_mean == 50.0
        assert summary.n_tasks == 1
        assert "does not estimate full-suite" in summary.message
