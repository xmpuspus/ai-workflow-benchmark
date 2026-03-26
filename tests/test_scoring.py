"""Tests for scoring module."""
from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
    TaskConstraints,
    TaskDefinition,
    TaskRepo,
    TaskVerification,
)
from awb.scoring.baselines import TaskBaselines
from awb.scoring.capabilities import compute_capability_profile
from awb.scoring.composite import compute_composite_score, compute_task_score, load_weight_profile
from awb.scoring.integrity import detect_contamination, detect_variance_anomalies
from awb.scoring.normalize import (
    normalize_cost,
    normalize_iterations,
    normalize_partial_credit,
    normalize_quality,
    normalize_regressions,
    normalize_security,
    normalize_speed,
    normalize_success_rate,
    sigmoid_normalize,
)
from awb.scoring.report import ScoreReport, generate_report
from awb.scoring.statistics import ScoredMetric, compare_tools_paired, scored_metric, t_ci


def _make_tool_stats(**overrides) -> dict:
    base = {
        "tool": "test-tool",
        "total_tasks": 10,
        "success_rate": 80.0,
        "avg_score_pct": 75.0,
        "avg_cost": 0.50,
        "avg_time": 200.0,
        "avg_iterations": 8.0,
        "total_lint_delta": 0,
        "total_security_delta": 0,
        "total_regressions": 0,
    }
    base.update(overrides)
    return base


def _make_result(task_id="BF-001", success=True, score=100, max_score=100,
                 cost=0.5, time=60.0, iterations=5, **kwargs) -> RunResult:
    return RunResult(
        task_id=task_id,
        tool="test-tool",
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        outcome=RunOutcome(success=success, partial_credit_score=score,
                           partial_credit_max=max_score),
        metrics=RunMetrics(wall_clock_seconds=time, iteration_count=iterations),
        cost=RunCost(estimated_cost_usd=cost),
        quality=RunQuality(),
        environment=RunEnvironment(os="test", hardware="test"),
    )


def _make_task(task_id="BF-001", difficulty="easy", estimated_minutes=15,
               capabilities=None) -> TaskDefinition:
    return TaskDefinition(
        id=task_id,
        category="bug-fix",
        title="Test task",
        difficulty=difficulty,
        estimated_minutes=estimated_minutes,
        languages=["python"],
        repo=TaskRepo(url="https://example.com", commit="abc123"),
        verification=TaskVerification(),
        constraints=TaskConstraints(),
        capabilities=capabilities or ["code_comprehension"],
    )


class TestSigmoidNormalize:
    def test_optimal_scores_high(self):
        score = sigmoid_normalize(10.0, 10.0, 100.0, lower_is_better=True)
        assert score > 90.0

    def test_baseline_scores_around_50(self):
        score = sigmoid_normalize(100.0, 10.0, 100.0, lower_is_better=True)
        assert 45.0 < score < 55.0

    def test_never_negative(self):
        score = sigmoid_normalize(10000.0, 10.0, 100.0, lower_is_better=True)
        assert score >= 0.0

    def test_never_above_100(self):
        score = sigmoid_normalize(0.0, 10.0, 100.0, lower_is_better=True)
        assert score <= 100.0

    def test_higher_is_better_mode(self):
        score = sigmoid_normalize(95.0, 100.0, 50.0, lower_is_better=False)
        assert score > 80.0

    def test_gradient_beyond_baseline(self):
        # Cost $3 should still have some score (not collapsed to 0)
        score = normalize_cost(3.0)
        assert score > 0.0
        # Cost $10 should score lower than $3
        score_10 = normalize_cost(10.0)
        assert score_10 < score


class TestNormalize:
    def test_success_rate_passthrough(self):
        assert normalize_success_rate(80.0) == 80.0

    def test_success_rate_clamped(self):
        assert normalize_success_rate(150.0) == 100.0
        assert normalize_success_rate(-10.0) == 0.0

    def test_partial_credit_passthrough(self):
        assert normalize_partial_credit(75.0) == 75.0

    def test_cost_lower_is_better(self):
        # Very low cost should score high
        assert normalize_cost(0.01) > 90.0
        # Moderate cost should score moderately
        mid = normalize_cost(1.0)
        assert 30 < mid < 70

    def test_quality_perfect(self):
        assert normalize_quality(0, 10) > 90.0

    def test_speed_lower_is_better(self):
        # Very fast should score high
        assert normalize_speed(10.0) > 90.0
        # Very slow should score low but not zero
        assert normalize_speed(1200.0) > 0.0

    def test_regressions_perfect(self):
        assert normalize_regressions(0, 10) > 90.0

    def test_security_perfect(self):
        assert normalize_security(0, 10) > 90.0

    def test_iterations_lower_is_better(self):
        # Few iterations should score high
        assert normalize_iterations(2.0) > 90.0
        # Many iterations should score low but not zero
        assert normalize_iterations(50.0) > 0.0


class TestCompositeScore:
    def test_legacy_mid_range(self):
        stats = _make_tool_stats()
        score = compute_composite_score(stats)
        assert 0 < score < 100

    def test_per_task_scoring(self):
        result = _make_result(success=True, score=100, cost=0.1, time=30.0, iterations=3)
        task = _make_task(difficulty="easy", estimated_minutes=15)
        ts = compute_task_score(result, task)
        assert ts.composite > 70.0
        assert "correctness" in ts.per_metric
        assert "speed" in ts.per_metric

    def test_difficulty_weighting(self):
        ts_easy = compute_task_score(
            _make_result(task_id="BF-001"), _make_task(task_id="BF-001", difficulty="easy")
        )
        ts_hard = compute_task_score(
            _make_result(task_id="MF-001"), _make_task(task_id="MF-001", difficulty="hard")
        )
        assert ts_easy.difficulty_weight < ts_hard.difficulty_weight

    def test_weight_profiles_load(self):
        default = load_weight_profile("default")
        assert abs(sum(default.values()) - 1.0) < 0.01
        production = load_weight_profile("production")
        assert abs(sum(production.values()) - 1.0) < 0.01


class TestBaselines:
    def test_from_task_easy(self):
        task = _make_task(difficulty="easy", estimated_minutes=15)
        b = TaskBaselines.from_task(task)
        assert b.cost_optimal == 0.05
        assert b.cost_baseline == 0.30
        assert b.speed_optimal == 15 * 30
        assert b.speed_baseline == 15 * 60

    def test_from_task_hard(self):
        task = _make_task(difficulty="hard", estimated_minutes=45)
        b = TaskBaselines.from_task(task)
        assert b.cost_optimal == 1.00
        assert b.cost_baseline == 3.00


class TestCapabilities:
    def test_profile_computes(self):
        results = [_make_result(task_id="BF-001", score=80, max_score=100)]
        tasks = {"BF-001": _make_task(
            task_id="BF-001", capabilities=["framework_knowledge", "test_writing"]
        )}
        profile = compute_capability_profile(results, tasks)
        assert profile.scores["framework_knowledge"].score == 80.0
        assert profile.scores["test_writing"].score == 80.0
        assert profile.scores["bug_diagnosis"].score is None

    def test_cost_discipline_derived(self):
        results = [_make_result(task_id="BF-001", cost=0.05)]
        tasks = {"BF-001": _make_task(task_id="BF-001")}
        profile = compute_capability_profile(results, tasks)
        assert profile.scores["cost_discipline"].score is not None
        assert profile.scores["cost_discipline"].score > 50.0


class TestStatistics:
    def test_t_ci_single_value(self):
        mean, lo, hi = t_ci([50.0])
        assert mean == 50.0
        assert lo == hi == 50.0

    def test_t_ci_multiple_values(self):
        mean, lo, hi = t_ci([80.0, 85.0, 90.0])
        assert lo < mean < hi
        assert 80.0 <= mean <= 90.0

    def test_scored_metric(self):
        sm = scored_metric([70.0, 80.0, 90.0])
        assert isinstance(sm, ScoredMetric)
        assert sm.n_runs == 3
        assert sm.sufficient is True

    def test_compare_tools_insufficient(self):
        result = compare_tools_paired([50.0, 60.0], [40.0, 45.0])
        assert result.significant is False
        assert "Need 5+" in result.message

    def test_compare_tools_significant(self):
        a = [90.0, 85.0, 80.0, 75.0, 70.0, 65.0]
        b = [30.0, 25.0, 20.0, 15.0, 10.0, 5.0]
        result = compare_tools_paired(a, b)
        assert result.mean_difference > 0
        assert result.significant is True


class TestIntegrity:
    def test_detects_fast_success(self):
        result = _make_result(success=True, time=5.0)
        warnings = detect_contamination([result])
        assert len(warnings) > 0
        assert any("pre-cached" in w.message.lower() or "5.0s" in w.message for w in warnings)

    def test_detects_zero_variance(self):
        results = [
            _make_result(task_id="BF-001", time=100.0),
            _make_result(task_id="BF-001", time=100.0),
            _make_result(task_id="BF-001", time=100.0),
        ]
        warnings = detect_variance_anomalies(results)
        assert len(warnings) > 0


class TestScoreReport:
    def test_dataclass(self):
        r = ScoreReport(tool="test", composite_score=75.0)
        assert r.tool == "test"
        assert r.composite_score == 75.0

    def test_generate_report(self):
        stats = _make_tool_stats()
        report = generate_report(stats)
        assert isinstance(report, ScoreReport)
        assert report.tool == "test-tool"
        assert 0 < report.composite_score < 100


def test_task_stability_stable():
    from awb.scoring.statistics import compute_task_stability
    s = compute_task_stability("BF-001", [80, 82, 78])
    assert not s.is_unstable
    assert s.std_dev < 3


def test_task_stability_unstable():
    from awb.scoring.statistics import compute_task_stability
    s = compute_task_stability("FA-003", [0, 90, 0])
    assert s.is_unstable
    assert s.score_range == 90


def test_stability_weight_stable():
    from awb.scoring.statistics import TaskStability, compute_stability_weights
    stabilities = [TaskStability("BF-001", 80, 5.0, 4.0, 3, False)]
    weights = compute_stability_weights(stabilities)
    assert weights["BF-001"] == 1.0


def test_stability_weight_unstable():
    from awb.scoring.statistics import TaskStability, compute_stability_weights
    stabilities = [TaskStability("FA-003", 30, 40.0, 90.0, 3, True)]
    weights = compute_stability_weights(stabilities)
    assert 0.3 < weights["FA-003"] < 1.0


def test_all_schema_capabilities_in_enum():
    """Every capability in schema.json must exist in Capability enum."""
    from awb.scoring.capabilities import Capability
    expected = {
        "code_comprehension", "bug_diagnosis", "multi_file_reasoning",
        "framework_knowledge", "test_writing", "refactoring_discipline",
        "security_awareness", "cost_discipline", "completeness_tracking",
        "convention_adherence", "context_discovery",
    }
    actual = {c.value for c in Capability}
    assert actual == expected
