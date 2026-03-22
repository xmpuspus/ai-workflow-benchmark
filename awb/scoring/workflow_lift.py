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


def compute_workflow_lift(
    vanilla_results: list[RunResult],
    custom_results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
) -> WorkflowLiftReport:
    """Compute how much the custom workflow improves over vanilla."""
    # Build lookup by task_id
    v_by_task = {r.task_id: r for r in vanilla_results}
    c_by_task = {r.task_id: r for r in custom_results}
    common = sorted(set(v_by_task) & set(c_by_task))

    if not common:
        return WorkflowLiftReport(
            lift=0, p_value=None, significant=False,
            vanilla_pass_rate=0, custom_pass_rate=0,
            vanilla_partial_avg=0, custom_partial_avg=0,
            n_tasks=0, custom_wins=0, vanilla_wins=0, ties=0,
        )

    # Per-task scores (partial credit percentage)
    v_scores = []
    c_scores = []
    per_task = []
    custom_wins = 0
    vanilla_wins = 0
    ties = 0

    for tid in common:
        vr = v_by_task[tid]
        cr = c_by_task[tid]
        v_max = vr.outcome.partial_credit_max or 1
        c_max = cr.outcome.partial_credit_max or 1
        vs = (vr.outcome.partial_credit_score / v_max) * 100
        cs = (cr.outcome.partial_credit_score / c_max) * 100
        v_scores.append(vs)
        c_scores.append(cs)

        delta = cs - vs
        if delta > 0.5:
            custom_wins += 1
        elif delta < -0.5:
            vanilla_wins += 1
        else:
            ties += 1

        per_task.append({
            "task_id": tid,
            "vanilla": round(vs, 1),
            "custom": round(cs, 1),
            "lift": round(delta, 1),
        })

    # Overall lift
    diffs = [c - v for v, c in zip(v_scores, c_scores, strict=False)]
    lift = stats_mod.mean(diffs)

    # Significance
    stat = compare_tools_paired(v_scores, c_scores)

    # Pass rates
    v_pass = sum(1 for tid in common if v_by_task[tid].outcome.success)
    c_pass = sum(1 for tid in common if c_by_task[tid].outcome.success)

    # Capability-level lift
    cap_v_scores: dict[str, list[float]] = defaultdict(list)
    cap_c_scores: dict[str, list[float]] = defaultdict(list)

    for tid in common:
        task = task_defs.get(tid)
        if not task:
            continue
        vr = v_by_task[tid]
        cr = c_by_task[tid]
        v_max = vr.outcome.partial_credit_max or 1
        c_max = cr.outcome.partial_credit_max or 1
        vs = (vr.outcome.partial_credit_score / v_max) * 100
        cs = (cr.outcome.partial_credit_score / c_max) * 100

        for cap in task.capabilities:
            cap_v_scores[cap].append(vs)
            cap_c_scores[cap].append(cs)

    capability_lifts = []
    for cap in sorted(cap_v_scores.keys()):
        v_avg = stats_mod.mean(cap_v_scores[cap])
        c_avg = stats_mod.mean(cap_c_scores[cap])
        capability_lifts.append(CapabilityLift(
            capability=cap,
            lift=round(c_avg - v_avg, 1),
            vanilla_avg=round(v_avg, 1),
            custom_avg=round(c_avg, 1),
            tasks=len(cap_v_scores[cap]),
        ))

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
    )
