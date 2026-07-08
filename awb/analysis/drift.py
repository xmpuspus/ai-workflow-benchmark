"""Drift detection - compare a fresh run against a reference and flag regressions.

The composite used here is a lightweight per-task mean score:
    mean(partial_credit_score / partial_credit_max * 100)
averaged across all runs of a task, then across all tasks. This intentionally
does not use the full Production Readiness Score (awb/scoring/readiness.py),
which needs task definitions loaded from the task registry. Drift is meant to
run cheaply in CI/cron against a run directory or a published baseline JSON
alone, so it sticks to the score dimension that both sources always carry.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReferenceScores:
    label: str
    per_task: dict[str, float]
    mean_score: float
    task_set_hash: str | None = None
    tool: str | None = None


@dataclass
class TaskRegression:
    task_id: str
    ref_score: float
    cur_score: float
    delta: float


@dataclass
class DriftReport:
    current_label: str
    reference_label: str
    mean_current: float
    mean_reference: float
    delta: float
    threshold: float
    drifted: bool
    regressions: list[TaskRegression] = field(default_factory=list)
    new_tasks: list[str] = field(default_factory=list)
    missing_tasks: list[str] = field(default_factory=list)
    task_set_hash_mismatch: bool = False


def _task_score_pct(score: float, max_score: float) -> float:
    return (score / max_score) * 100 if max_score else 0.0


def _per_task_scores(results) -> dict[str, list[float]]:
    by_task: dict[str, list[float]] = {}
    for r in results:
        pct = _task_score_pct(r.outcome.partial_credit_score, r.outcome.partial_credit_max)
        by_task.setdefault(r.task_id, []).append(pct)
    return by_task


def _mean_per_task(by_task: dict[str, list[float]]) -> dict[str, float]:
    return {tid: statistics.mean(scores) for tid, scores in by_task.items()}


def _single_task_set_hash(results) -> str | None:
    hashes = {r.task_set_hash for r in results if r.task_set_hash}
    return next(iter(hashes)) if len(hashes) == 1 else None


def _single_tool(results) -> str | None:
    tools = {r.tool for r in results if r.tool}
    return next(iter(tools)) if len(tools) == 1 else None


def _reference_from_results(label: str, results) -> ReferenceScores:
    per_task = _mean_per_task(_per_task_scores(results))
    mean_score = statistics.mean(per_task.values()) if per_task else 0.0
    return ReferenceScores(
        label=label,
        per_task=per_task,
        mean_score=round(mean_score, 1),
        task_set_hash=_single_task_set_hash(results),
        tool=_single_tool(results),
    )


def load_reference(path: str | Path) -> ReferenceScores:
    """Load per-task mean scores from a run directory or an awb/v2 baseline JSON.

    Accepts either:
    - a directory of `*.json` per-task result files, as produced by `awb run`
    - a single awb/v2 baseline/submission JSON file, as under results/baselines/
    """
    p = Path(path)
    if p.is_dir():
        from awb.core.results import ResultRecorder

        results = ResultRecorder().load_run(p)
        return _reference_from_results(p.name, results)

    with p.open() as f:
        data = json.load(f)
    if not (isinstance(data, dict) and data.get("spec_version") == "awb/v2"):
        raise ValueError(f"{p} is not a directory or an awb/v2 baseline JSON file")

    from awb.submission.ingest import load_submission, submission_to_run_results

    submission = load_submission(p)
    results = submission_to_run_results(submission)
    per_task = _mean_per_task(_per_task_scores(results))
    mean_score = statistics.mean(per_task.values()) if per_task else 0.0
    return ReferenceScores(
        label=p.stem,
        per_task=per_task,
        mean_score=round(mean_score, 1),
        task_set_hash=submission.task_set_hash or None,
        tool=submission.tool.name or None,
    )


def compute_drift(
    current: ReferenceScores, reference: ReferenceScores, threshold: float
) -> DriftReport:
    """Diff two ReferenceScores. Drifted when mean_current drops more than threshold.

    `regressions` lists only tasks whose score fell (delta < 0), worst first -
    the tasks worth looking at when the composite has drifted.
    """
    common = sorted(set(current.per_task) & set(reference.per_task))
    new_tasks = sorted(set(current.per_task) - set(reference.per_task))
    missing_tasks = sorted(set(reference.per_task) - set(current.per_task))

    regressions = [
        TaskRegression(
            task_id=tid,
            ref_score=reference.per_task[tid],
            cur_score=current.per_task[tid],
            delta=current.per_task[tid] - reference.per_task[tid],
        )
        for tid in common
        if current.per_task[tid] - reference.per_task[tid] < 0
    ]
    regressions.sort(key=lambda r: r.delta)

    delta = current.mean_score - reference.mean_score
    task_set_hash_mismatch = bool(
        current.task_set_hash
        and reference.task_set_hash
        and current.task_set_hash != reference.task_set_hash
    )

    return DriftReport(
        current_label=current.label,
        reference_label=reference.label,
        mean_current=round(current.mean_score, 1),
        mean_reference=round(reference.mean_score, 1),
        delta=round(delta, 1),
        threshold=threshold,
        drifted=delta < -threshold,
        regressions=regressions,
        new_tasks=new_tasks,
        missing_tasks=missing_tasks,
        task_set_hash_mismatch=task_set_hash_mismatch,
    )
