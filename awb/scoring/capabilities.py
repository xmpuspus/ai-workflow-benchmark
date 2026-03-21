"""Capability profiling — radar chart data showing tool strengths and weaknesses."""
from __future__ import annotations

import statistics as stats_mod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

from awb.core.config import RunResult, TaskDefinition
from awb.scoring.baselines import TaskBaselines
from awb.scoring.normalize import sigmoid_normalize


class Capability(StrEnum):
    CODE_COMPREHENSION = "code_comprehension"
    BUG_DIAGNOSIS = "bug_diagnosis"
    MULTI_FILE_REASONING = "multi_file_reasoning"
    FRAMEWORK_KNOWLEDGE = "framework_knowledge"
    TEST_WRITING = "test_writing"
    REFACTORING_DISCIPLINE = "refactoring_discipline"
    SECURITY_AWARENESS = "security_awareness"
    COST_DISCIPLINE = "cost_discipline"


@dataclass
class CapabilityScore:
    score: float | None  # None if not tested
    tasks_tested: int
    confidence: float  # 0.0-1.0

@dataclass
class CapabilityProfile:
    scores: dict[str, CapabilityScore] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            k: {"score": v.score, "tasks_tested": v.tasks_tested, "confidence": v.confidence}
            for k, v in self.scores.items()
        }


def compute_capability_profile(
    results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
) -> CapabilityProfile:
    """Compute capability radar from results mapped to task capabilities."""
    capability_scores: dict[str, list[float]] = defaultdict(list)

    for result in results:
        task = task_defs.get(result.task_id)
        if not task:
            continue

        max_pts = result.outcome.partial_credit_max or 1
        task_score = (result.outcome.partial_credit_score / max_pts) * 100

        for cap in task.capabilities:
            capability_scores[cap].append(task_score)

    profile = CapabilityProfile()
    for cap in Capability:
        if cap == Capability.COST_DISCIPLINE:
            # Derived from cost metrics, not task mapping
            cost_score = _compute_cost_discipline(results, task_defs)
            n = len(results)
            profile.scores[cap.value] = CapabilityScore(
                score=cost_score,
                tasks_tested=n,
                confidence=min(0.9, 0.2 + 0.1 * n) if n else 0.0,
            )
            continue

        cap_results = capability_scores.get(cap.value, [])
        n = len(cap_results)
        if n:
            profile.scores[cap.value] = CapabilityScore(
                score=round(stats_mod.mean(cap_results), 1),
                tasks_tested=n,
                confidence=min(0.9, 0.2 + 0.1 * n),
            )
        else:
            profile.scores[cap.value] = CapabilityScore(
                score=None,
                tasks_tested=0,
                confidence=0.0,
            )

    return profile


def _compute_cost_discipline(
    results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
) -> float | None:
    """Score 0-100 based on how efficiently the tool uses tokens."""
    cost_scores = []
    for result in results:
        task = task_defs.get(result.task_id)
        if not task:
            continue
        baselines = TaskBaselines.from_task(task)
        cost_score = sigmoid_normalize(
            result.cost.estimated_cost_usd,
            baselines.cost_optimal,
            baselines.cost_baseline,
            lower_is_better=True,
        )
        cost_scores.append(cost_score)
    if not cost_scores:
        return None
    return round(stats_mod.mean(cost_scores), 1)
