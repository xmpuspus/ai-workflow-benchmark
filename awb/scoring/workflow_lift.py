"""Workflow Lift Score — measures how much a workflow contributes vs vanilla."""

from __future__ import annotations

import statistics as stats_mod
from collections import defaultdict
from dataclasses import dataclass, field

from awb.core.config import RunResult, TaskDefinition
from awb.scoring.statistics import compare_tools_paired


@dataclass
class CapabilityLift:
    capability: str
    lift: float  # positive = workflow helps
    vanilla_avg: float
    custom_avg: float
    tasks: int


@dataclass
class WorkflowLiftReport:
    lift: float  # overall workflow contribution in points
    p_value: float | None
    significant: bool
    vanilla_pass_rate: float
    custom_pass_rate: float
    vanilla_partial_avg: float
    custom_partial_avg: float
    n_tasks: int
    custom_wins: int
    vanilla_wins: int
    ties: int
    capability_lifts: list[CapabilityLift] = field(default_factory=list)
    per_task: list[dict] = field(default_factory=list)
    aggregation: str = "mean_per_task"
    total_attempts_vanilla: int = 0
    total_attempts_custom: int = 0
    unpaired_attempts_vanilla: int = 0
    unpaired_attempts_custom: int = 0


def compute_workflow_lift(
    vanilla_results: list[RunResult],
    custom_results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
) -> WorkflowLiftReport:
    """Compute how much the custom workflow improves over vanilla."""
    # Build lookup by task_id
    v_by_task: dict[str, list[RunResult]] = defaultdict(list)
    c_by_task: dict[str, list[RunResult]] = defaultdict(list)
    for result in vanilla_results:
        v_by_task[result.task_id].append(result)
    for result in custom_results:
        c_by_task[result.task_id].append(result)
    common = sorted(set(v_by_task) & set(c_by_task))

    if not common:
        return WorkflowLiftReport(
            lift=0,
            p_value=None,
            significant=False,
            vanilla_pass_rate=0,
            custom_pass_rate=0,
            vanilla_partial_avg=0,
            custom_partial_avg=0,
            n_tasks=0,
            custom_wins=0,
            vanilla_wins=0,
            ties=0,
            total_attempts_vanilla=len(vanilla_results),
            total_attempts_custom=len(custom_results),
            unpaired_attempts_vanilla=len(vanilla_results),
            unpaired_attempts_custom=len(custom_results),
        )

    # Per-task scores (partial credit percentage)
    v_scores = []
    c_scores = []
    per_task = []
    custom_wins = 0
    vanilla_wins = 0
    ties = 0

    for tid in common:
        vanilla_attempts = v_by_task[tid]
        custom_attempts = c_by_task[tid]
        vs = stats_mod.mean(
            (r.outcome.partial_credit_score / (r.outcome.partial_credit_max or 1)) * 100
            for r in vanilla_attempts
        )
        cs = stats_mod.mean(
            (r.outcome.partial_credit_score / (r.outcome.partial_credit_max or 1)) * 100
            for r in custom_attempts
        )
        v_scores.append(vs)
        c_scores.append(cs)

        delta = cs - vs
        if delta > 0.5:
            custom_wins += 1
        elif delta < -0.5:
            vanilla_wins += 1
        else:
            ties += 1

        per_task.append(
            {
                "task_id": tid,
                "vanilla": round(vs, 1),
                "custom": round(cs, 1),
                "lift": round(delta, 1),
                "vanilla_attempts": len(vanilla_attempts),
                "custom_attempts": len(custom_attempts),
            }
        )

    # Overall lift
    diffs = [c - v for v, c in zip(v_scores, c_scores, strict=False)]
    lift = stats_mod.mean(diffs)

    # Significance
    stat = compare_tools_paired(v_scores, c_scores)

    # Pass rates
    v_pass = sum(stats_mod.mean(r.outcome.success for r in v_by_task[tid]) for tid in common)
    c_pass = sum(stats_mod.mean(r.outcome.success for r in c_by_task[tid]) for tid in common)

    # Capability-level lift
    cap_v_scores: dict[str, list[float]] = defaultdict(list)
    cap_c_scores: dict[str, list[float]] = defaultdict(list)

    for tid in common:
        task = task_defs.get(tid)
        if not task:
            continue
        vs = stats_mod.mean(
            (r.outcome.partial_credit_score / (r.outcome.partial_credit_max or 1)) * 100
            for r in v_by_task[tid]
        )
        cs = stats_mod.mean(
            (r.outcome.partial_credit_score / (r.outcome.partial_credit_max or 1)) * 100
            for r in c_by_task[tid]
        )

        for cap in task.capabilities:
            cap_v_scores[cap].append(vs)
            cap_c_scores[cap].append(cs)

    capability_lifts = []
    for cap in sorted(cap_v_scores.keys()):
        v_avg = stats_mod.mean(cap_v_scores[cap])
        c_avg = stats_mod.mean(cap_c_scores[cap])
        capability_lifts.append(
            CapabilityLift(
                capability=cap,
                lift=round(c_avg - v_avg, 1),
                vanilla_avg=round(v_avg, 1),
                custom_avg=round(c_avg, 1),
                tasks=len(cap_v_scores[cap]),
            )
        )

    # Sort by lift descending
    capability_lifts.sort(key=lambda x: -x.lift)

    return WorkflowLiftReport(
        lift=round(lift, 1),
        p_value=stat.p_value,
        significant=stat.significant,
        vanilla_pass_rate=round(v_pass / len(common) * 100, 1),
        custom_pass_rate=round(c_pass / len(common) * 100, 1),
        vanilla_partial_avg=round(stats_mod.mean(v_scores), 1),
        custom_partial_avg=round(stats_mod.mean(c_scores), 1),
        n_tasks=len(common),
        custom_wins=custom_wins,
        vanilla_wins=vanilla_wins,
        ties=ties,
        capability_lifts=capability_lifts,
        per_task=sorted(per_task, key=lambda x: -abs(x["lift"])),
        total_attempts_vanilla=len(vanilla_results),
        total_attempts_custom=len(custom_results),
        unpaired_attempts_vanilla=sum(len(v) for k, v in v_by_task.items() if k not in common),
        unpaired_attempts_custom=sum(len(v) for k, v in c_by_task.items() if k not in common),
    )
