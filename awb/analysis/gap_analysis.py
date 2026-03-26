"""Gap analysis engine — explains failures and identifies systematic weaknesses."""

from __future__ import annotations

import statistics as stats_mod
from collections import defaultdict
from dataclasses import dataclass, field

from awb.analysis.suggestions import get_suggestions
from awb.core.config import RunResult, TaskDefinition
from awb.scoring.capabilities import CapabilityProfile, compute_capability_profile


@dataclass
class FailureAnalysis:
    task_id: str
    task_title: str
    capabilities_tested: list[str]
    failure_category: str  # timeout, test_error, partial_completion, code_error
    partial_credit_pct: float
    criteria_passed: list[str]
    criteria_failed: list[str]
    suggestions: list[str]


@dataclass
class GapReport:
    tool: str
    overall_score: float
    capability_profile: CapabilityProfile
    failure_analyses: list[FailureAnalysis] = field(default_factory=list)
    systematic_patterns: list[str] = field(default_factory=list)
    top_improvement_actions: list[str] = field(default_factory=list)


def classify_failure(result: RunResult, task: TaskDefinition) -> str:
    """Classify the type of failure for a task result."""
    if result.outcome.success:
        return "success"

    if result.metrics.wall_clock_seconds >= task.constraints.timeout_seconds * 0.95:
        return "timeout"

    # Check if tests were attempted but failed
    has_test_criteria = any(
        "test" in c.criterion.lower() or "pass" in c.criterion.lower()
        for c in result.outcome.breakdown
    )
    test_criteria_failed = any(
        ("test" in c.criterion.lower() or "pass" in c.criterion.lower()) and not c.passed
        for c in result.outcome.breakdown
    )
    if has_test_criteria and test_criteria_failed:
        return "test_error"

    if result.outcome.partial_credit_score > 0:
        return "partial_completion"

    return "code_error"


def analyze_failure(
    result: RunResult,
    task: TaskDefinition,
) -> FailureAnalysis:
    """Generate a detailed analysis for a single failed/partial task."""
    failure_cat = classify_failure(result, task)
    max_pts = result.outcome.partial_credit_max or 1
    pct = (result.outcome.partial_credit_score / max_pts) * 100

    passed = [c.criterion for c in result.outcome.breakdown if c.passed]
    failed = [c.criterion for c in result.outcome.breakdown if not c.passed]

    suggestions = get_suggestions(failure_cat, task.capabilities)

    return FailureAnalysis(
        task_id=result.task_id,
        task_title=task.title,
        capabilities_tested=task.capabilities,
        failure_category=failure_cat,
        partial_credit_pct=round(pct, 1),
        criteria_passed=passed,
        criteria_failed=failed,
        suggestions=suggestions,
    )


def detect_patterns(
    results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
) -> list[str]:
    """Find recurring failure patterns across tasks."""
    patterns = []

    # Pattern: fails most tasks requiring a specific capability
    cap_results: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        task = task_defs.get(r.task_id)
        if not task:
            continue
        for cap in task.capabilities:
            cap_results[cap].append(r.outcome.success)

    for cap, successes in cap_results.items():
        if len(successes) >= 2:
            fail_count = sum(1 for s in successes if not s)
            fail_rate = fail_count / len(successes)
            if fail_rate >= 0.7:
                cap_label = cap.replace("_", " ")
                patterns.append(
                    f"Systematic weakness in {cap_label}: "
                    f"failed {fail_count}/{len(successes)} tasks"
                )

    # Pattern: passes easy, fails hard (difficulty cliff)
    by_diff: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        task = task_defs.get(r.task_id)
        if task:
            by_diff[task.difficulty].append(r.outcome.success)

    easy_results = by_diff.get("easy", [])
    hard_results = by_diff.get("hard", [])
    if easy_results and hard_results:
        easy_rate = sum(easy_results) / len(easy_results)
        hard_rate = sum(hard_results) / len(hard_results)
        if easy_rate > 0.8 and hard_rate < 0.3:
            patterns.append(
                f"Difficulty cliff: {easy_rate:.0%} pass rate on easy tasks, "
                f"{hard_rate:.0%} on hard. Tool handles simple tasks but struggles with complexity."
            )

    # Pattern: high cost but low success (token burning)
    for r in results:
        if not r.outcome.success and r.cost.estimated_cost_usd > 1.0:
            patterns.append(
                f"Task {r.task_id}: spent ${r.cost.estimated_cost_usd:.2f} but failed. "
                f"Consider adding early-exit or problem decomposition to workflow."
            )

    return patterns


def _rank_improvement_actions(
    failure_analyses: list[FailureAnalysis],
) -> list[str]:
    """Rank improvement suggestions by frequency across failures."""
    suggestion_count: dict[str, int] = defaultdict(int)
    for fa in failure_analyses:
        for s in fa.suggestions:
            suggestion_count[s] += 1

    ranked = sorted(suggestion_count.items(), key=lambda x: -x[1])
    return [s for s, _ in ranked[:5]]


def generate_gap_report(
    results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
    tool_name: str = "",
) -> GapReport:
    """Generate a complete gap analysis report."""
    if not tool_name and results:
        tool_name = results[0].tool

    profile = compute_capability_profile(results, task_defs)

    # Analyze failures
    failure_analyses = []
    for r in results:
        task = task_defs.get(r.task_id)
        if not task:
            continue
        if not r.outcome.success:
            failure_analyses.append(analyze_failure(r, task))

    patterns = detect_patterns(results, task_defs)
    top_actions = _rank_improvement_actions(failure_analyses)

    # Overall score: mean partial credit across all tasks
    if results:
        scores = []
        for r in results:
            max_pts = r.outcome.partial_credit_max or 1
            scores.append((r.outcome.partial_credit_score / max_pts) * 100)
        overall = round(stats_mod.mean(scores), 1)
    else:
        overall = 0.0

    return GapReport(
        tool=tool_name,
        overall_score=overall,
        capability_profile=profile,
        failure_analyses=failure_analyses,
        systematic_patterns=patterns,
        top_improvement_actions=top_actions,
    )
