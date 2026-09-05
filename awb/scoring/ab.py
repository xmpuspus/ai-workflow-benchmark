"""Config A/B report - pairs same-adapter runs across two config directories.

Answers "I changed my CLAUDE.md - did it help?" by running the same tool twice
(once per config dir) over the same tasks, then pairing per-task scores and
running the existing paired sign test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from awb.core.config import RunResult
from awb.scoring.statistics import compare_tools_paired


@dataclass
class ABTaskDelta:
    task_id: str
    score_a: float
    score_b: float
    delta: float  # score_b - score_a; positive means config B scored higher
    attempts_a: int = 1
    attempts_b: int = 1


@dataclass
class ABReport:
    tool: str
    config_a: str
    config_b: str
    n_tasks: int
    mean_delta: float
    p_value: float | None
    significant: bool
    effect_size: float
    per_task: list[ABTaskDelta] = field(default_factory=list)
    config_hash_a: str = ""
    config_hash_b: str = ""
    message: str = ""
    aggregation: str = "mean_per_task"
    total_attempts_a: int = 0
    total_attempts_b: int = 0
    unpaired_attempts_a: int = 0
    unpaired_attempts_b: int = 0


def _task_score(result: RunResult) -> float:
    max_pts = result.outcome.partial_credit_max or 1
    return (result.outcome.partial_credit_score / max_pts) * 100


def _verdict_message(label_a: str, label_b: str, mean_delta: float, stat) -> str:
    if stat.p_value is None:
        return stat.message
    if not stat.significant:
        return f"No significant difference between {label_a} and {label_b} (p={stat.p_value:.3f})"
    winner, loser = (label_b, label_a) if mean_delta > 0 else (label_a, label_b)
    return (
        f"{winner} scores higher than {loser}. "
        f"Effect: {stat.effect_interpretation} (p={stat.p_value:.3f})."
    )


def build_ab_report(
    results_a: list[RunResult],
    results_b: list[RunResult],
    label_a: str,
    label_b: str,
    config_hash_a: str = "",
    config_hash_b: str = "",
) -> ABReport:
    """Pair per-task scores across config A/B runs and run a paired sign test.

    Pairing is by task_id; tasks present in only one of the two result sets
    are dropped. Score per task is partial_credit_score/max scaled to 0-100.
    """
    a_by_task: dict[str, list[RunResult]] = {}
    b_by_task: dict[str, list[RunResult]] = {}
    for result in results_a:
        a_by_task.setdefault(result.task_id, []).append(result)
    for result in results_b:
        b_by_task.setdefault(result.task_id, []).append(result)
    common = sorted(set(a_by_task) & set(b_by_task))

    tool = results_a[0].tool if results_a else (results_b[0].tool if results_b else "")

    if not common:
        return ABReport(
            tool=tool,
            config_a=label_a,
            config_b=label_b,
            n_tasks=0,
            mean_delta=0.0,
            p_value=None,
            significant=False,
            effect_size=0.0,
            per_task=[],
            config_hash_a=config_hash_a,
            config_hash_b=config_hash_b,
            message="No shared tasks between config A and config B runs",
            total_attempts_a=len(results_a),
            total_attempts_b=len(results_b),
            unpaired_attempts_a=len(results_a),
            unpaired_attempts_b=len(results_b),
        )

    scores_a = []
    scores_b = []
    per_task = []
    for tid in common:
        attempts_a = a_by_task[tid]
        attempts_b = b_by_task[tid]
        sa = mean(_task_score(result) for result in attempts_a)
        sb = mean(_task_score(result) for result in attempts_b)
        scores_a.append(sa)
        scores_b.append(sb)
        per_task.append(
            ABTaskDelta(
                task_id=tid,
                score_a=round(sa, 1),
                score_b=round(sb, 1),
                delta=round(sb - sa, 1),
                attempts_a=len(attempts_a),
                attempts_b=len(attempts_b),
            )
        )

    # scores_b first so ComparisonResult's diffs/mean_difference/effect_size
    # read as (B - A), matching this module's delta convention.
    stat = compare_tools_paired(scores_b, scores_a)

    return ABReport(
        tool=tool,
        config_a=label_a,
        config_b=label_b,
        n_tasks=len(common),
        mean_delta=stat.mean_difference,
        p_value=stat.p_value,
        significant=stat.significant,
        effect_size=stat.effect_size,
        per_task=sorted(per_task, key=lambda d: -abs(d.delta)),
        config_hash_a=config_hash_a,
        config_hash_b=config_hash_b,
        message=_verdict_message(label_a, label_b, stat.mean_difference, stat),
        total_attempts_a=len(results_a),
        total_attempts_b=len(results_b),
        unpaired_attempts_a=sum(len(v) for k, v in a_by_task.items() if k not in common),
        unpaired_attempts_b=sum(len(v) for k, v in b_by_task.items() if k not in common),
    )
