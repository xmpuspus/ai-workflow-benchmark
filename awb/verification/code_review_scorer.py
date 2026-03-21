from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FINDING_RE = re.compile(r"issue|bug|vulnerability|problem", re.IGNORECASE)


@dataclass
class ReviewScore:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


async def score_code_review(
    review_output: str,
    known_issues: list[str],
    workspace: Path,
) -> ReviewScore:
    """Score a code review against known issues."""
    lower_output = review_output.lower()

    true_positives = sum(1 for issue in known_issues if issue.lower() in lower_output)
    false_negatives = len(known_issues) - true_positives

    total_findings = sum(1 for line in review_output.splitlines() if _FINDING_RE.search(line))
    false_positives = max(0, total_findings - true_positives)

    denom_p = true_positives + false_positives
    denom_r = true_positives + false_negatives
    precision = true_positives / denom_p if denom_p > 0 else 0.0
    recall = true_positives / denom_r if denom_r > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return ReviewScore(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
    )
