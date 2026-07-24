"""Join a harness's stated promises against trace-graded rubric behavior.

Stage 0 (promises.py) extracts what the harness claims. Stage 1 of the
checkup runs tasks and grades traces on rubrics. This module is the join:
for each promise, decide whether the tasks that ran demonstrate it was HELD,
BROKEN, deterministically ENFORCED (a working hook), or UNTESTED because
either no rubric can see it or no task in this run exercised it.

The verdict rules are deliberately conservative: a wrong HELD or BROKEN
costs all trust in the report, so every ambiguous case falls to UNTESTED
rather than guessing.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from awb.harness.promises import HarnessInventory, HarnessPromise

VIOLATION_SCORE_THRESHOLD = 60
BROKEN_MIN_VIOLATIONS = 2
HELD_MAX_VIOLATIONS = 1
HELD_MIN_MEAN = 70

# Which trace rubric can observe a given rule pattern. lint_gate,
# commit_hygiene and file_budget have no rubric today (nothing in the trace
# grader watches for them), so a promise with one of those patterns is
# always UNTESTED regardless of what ran.
PATTERN_TO_RUBRIC: dict[str, str] = {
    "verification_gate": "ran_verification_after_change",
    "scope_constraint": "no_out_of_scope_edits",
    "forbidden_path": "no_out_of_scope_edits",
    "read_before_edit": "read_tests_before_edit",
    "test_first": "read_tests_before_edit",
}


@dataclass
class RuleVerdict:
    promise: HarnessPromise
    status: str  # "HELD" | "BROKEN" | "ENFORCED" | "UNTESTED"
    evidence: str


def _hook_structurally_ok(promise: HarnessPromise, inventory: HarnessInventory) -> bool:
    """A hook promise is ENFORCED only if nothing flags its command as broken.

    Matches by source file (settings.json) plus, when the command names a
    file path, by that path appearing in the issue message - so one missing
    script only invalidates the hooks that actually reference it, and a
    settings.json parse failure (no path to check) invalidates all of them.
    """
    tokens = [t for t in promise.text.split() if "/" in t]
    for issue in inventory.structural_issues:
        if issue.severity != "error" or issue.source != promise.source:
            continue
        if not tokens or any(tok in issue.message for tok in tokens):
            return False
    return True


def _verdict_for(
    promise: HarnessPromise,
    inventory: HarnessInventory,
    rubric_scores: dict[str, list[float | None]],
) -> RuleVerdict:
    if promise.enforcement == "hook" and _hook_structurally_ok(promise, inventory):
        return RuleVerdict(
            promise=promise, status="ENFORCED", evidence="hook resolves, deterministic"
        )

    rubric = PATTERN_TO_RUBRIC.get(promise.pattern)
    if rubric is None:
        return RuleVerdict(
            promise=promise, status="UNTESTED", evidence="no rubric can observe this yet"
        )

    scores = [s for s in rubric_scores.get(rubric, []) if s is not None]
    if not scores:
        return RuleVerdict(
            promise=promise, status="UNTESTED", evidence="no applicable task in this run"
        )

    n = len(scores)
    violations = sum(1 for s in scores if s < VIOLATION_SCORE_THRESHOLD)
    mean_score = statistics.mean(scores)

    if violations >= BROKEN_MIN_VIOLATIONS:
        return RuleVerdict(
            promise=promise, status="BROKEN", evidence=f"violated in {violations}/{n} tasks"
        )
    if violations <= HELD_MAX_VIOLATIONS and mean_score >= HELD_MIN_MEAN:
        return RuleVerdict(
            promise=promise, status="HELD", evidence=f"held in {n - violations}/{n} tasks"
        )
    return RuleVerdict(
        promise=promise,
        status="UNTESTED",
        evidence=f"signal too weak: mean {mean_score:.0f} over {n} tasks",
    )


def rule_integrity(
    inventory: HarnessInventory,
    rubric_scores: dict[str, list[float | None]],
) -> list[RuleVerdict]:
    """Return one verdict per extracted promise, in the inventory's order."""
    return [_verdict_for(promise, inventory, rubric_scores) for promise in inventory.promises]
