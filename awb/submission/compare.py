"""Cross-submission comparison with statistical significance."""

from __future__ import annotations

import statistics as stats_mod
from dataclasses import dataclass, field

from awb.scoring.statistics import ComparisonResult, compare_tools_paired
from awb.submission.schema import Submission


@dataclass
class SubmissionComparison:
    tool_a: str
    tool_b: str
    common_tasks: int
    total_tasks_a: int
    total_tasks_b: int
    hardware_comparable: bool
    hardware_warning: str
    scores_a: dict[str, float] = field(default_factory=dict)
    scores_b: dict[str, float] = field(default_factory=dict)
    statistical_comparison: ComparisonResult | None = None
    per_task: list[dict] = field(default_factory=list)
    comparison_eligible: bool = False
    eligibility_warning: str = ""


def find_common_tasks(sub_a: Submission, sub_b: Submission) -> set[str]:
    """Return task IDs present in both submissions."""
    tasks_a = {r.task_id for r in sub_a.results}
    tasks_b = {r.task_id for r in sub_b.results}
    return tasks_a & tasks_b


def compare_submissions(
    sub_a: Submission,
    sub_b: Submission,
) -> SubmissionComparison:
    """Compare two external submissions on their common task subset."""
    common = find_common_tasks(sub_a, sub_b)
    hw_same = sub_a.environment.hardware_class == sub_b.environment.hardware_class
    hw_warning = ""
    if not hw_same:
        hw_warning = (
            f"Different hardware: {sub_a.environment.hardware_class} vs "
            f"{sub_b.environment.hardware_class}. "
            f"Speed and efficiency scores are not directly comparable."
        )

    eligibility_reasons = []
    if not sub_a.comparison_eligible:
        eligibility_reasons.append(f"{sub_a.tool.name}: {', '.join(sub_a.ineligibility_reasons)}")
    if not sub_b.comparison_eligible:
        eligibility_reasons.append(f"{sub_b.tool.name}: {', '.join(sub_b.ineligibility_reasons)}")
    if (
        sub_a.comparison_eligible
        and sub_b.comparison_eligible
        and sub_a.comparison_identity != sub_b.comparison_identity
    ):
        eligibility_reasons.append("comparison identities differ")

    if eligibility_reasons:
        return SubmissionComparison(
            tool_a=sub_a.tool.name,
            tool_b=sub_b.tool.name,
            common_tasks=len(common),
            total_tasks_a=len(sub_a.results),
            total_tasks_b=len(sub_b.results),
            hardware_comparable=hw_same,
            hardware_warning=hw_warning,
            eligibility_warning="; ".join(eligibility_reasons),
        )

    if len(common) < 5:
        return SubmissionComparison(
            tool_a=sub_a.tool.name,
            tool_b=sub_b.tool.name,
            common_tasks=len(common),
            total_tasks_a=len(sub_a.results),
            total_tasks_b=len(sub_b.results),
            hardware_comparable=hw_same,
            hardware_warning=hw_warning or "Insufficient task overlap (need 5+) for comparison",
            comparison_eligible=True,
        )

    def _task_median_score(results, task_id):
        for r in results:
            if r.task_id == task_id:
                scores = []
                for run in r.runs:
                    max_pts = run.outcome.partial_credit_max or 1
                    scores.append((run.outcome.partial_credit_score / max_pts) * 100)
                return stats_mod.median(scores) if scores else 0.0
        return 0.0

    scores_a_list = []
    scores_b_list = []
    per_task = []

    for tid in sorted(common):
        sa = _task_median_score(sub_a.results, tid)
        sb = _task_median_score(sub_b.results, tid)
        scores_a_list.append(sa)
        scores_b_list.append(sb)
        per_task.append({"task_id": tid, "score_a": round(sa, 1), "score_b": round(sb, 1)})

    stat_result = compare_tools_paired(scores_a_list, scores_b_list)

    agg_a = round(stats_mod.mean(scores_a_list), 1) if scores_a_list else 0.0
    agg_b = round(stats_mod.mean(scores_b_list), 1) if scores_b_list else 0.0

    return SubmissionComparison(
        tool_a=sub_a.tool.name,
        tool_b=sub_b.tool.name,
        common_tasks=len(common),
        total_tasks_a=len(sub_a.results),
        total_tasks_b=len(sub_b.results),
        hardware_comparable=hw_same,
        hardware_warning=hw_warning,
        scores_a={"aggregate": agg_a},
        scores_b={"aggregate": agg_b},
        statistical_comparison=stat_result,
        per_task=per_task,
        comparison_eligible=True,
    )
