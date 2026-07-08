"""Prescriptive gap output: turns rubric failures and capability gaps into
concrete, copy-pasteable CLAUDE.md fixes with the evidence behind each one.

This is a deeper layer on top of awb/analysis/suggestions.py: suggestions.py
maps a failure category to a one-line nudge, this module maps a *sustained*
trace-rubric or capability weakness (multiple tasks, not one) to a full
config snippet plus the task-level evidence that triggered it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from awb.core.config import RunResult, TaskDefinition
from awb.scoring.capabilities import compute_capability_profile
from awb.trace.grader import grade_trace_or_none

RUBRIC_SCORE_THRESHOLD = 60
RUBRIC_MIN_LOW_TASKS = 2
CAPABILITY_SCORE_THRESHOLD = 60
CAPABILITY_MIN_TASKS = 2


@dataclass
class Prescription:
    id: str
    trigger: str
    evidence: list[str]
    affected_tasks: list[str]
    severity: int
    snippet: str
    rationale: str


@dataclass
class PrescriptionReport:
    tool: str
    prescriptions: list[Prescription] = field(default_factory=list)
    n_traces_graded: int = 0
    n_traces_missing: int = 0


# Deterministic rubric name -> CLAUDE.md fix. Content mirrors the workflow
# disciplines the trace grader actually scores (awb/trace/grader.py).
RUBRIC_PRESCRIPTIONS: dict[str, dict[str, str]] = {
    "no_out_of_scope_edits": {
        "id": "rubric-no_out_of_scope_edits",
        "rationale": (
            "The tool edited files outside the task's declared scope on multiple "
            "tasks, which is a common cause of PR review friction."
        ),
        "snippet": (
            "## Scope Discipline\n"
            "\n"
            "- Parse the task's file and change constraints before writing any code.\n"
            "- Touch only the files named in the request. If a fix needs a file that "
            "is not listed, say so and wait instead of editing it.\n"
            "- Before declaring the task done, run `git diff --name-only` and revert "
            "any file that is not on the approved list.\n"
        ),
    },
    "read_tests_before_edit": {
        "id": "rubric-read_tests_before_edit",
        "rationale": (
            "The tool edited source files without reading the tests that cover them "
            "first, so it was guessing at expected behavior instead of confirming it."
        ),
        "snippet": (
            "## Read Tests Before Editing\n"
            "\n"
            "- Before changing any source file, read the failing test and its "
            "fixtures first. The test is the specification.\n"
            "- If no test covers the change, say so before editing instead of "
            "guessing at the expected behavior.\n"
        ),
    },
    "ran_verification_after_change": {
        "id": "rubric-ran_verification_after_change",
        "rationale": (
            "The tool made edits but did not re-run the test suite afterward, so "
            "there is no evidence the change works."
        ),
        "snippet": (
            "## Verify After Every Change\n"
            "\n"
            "- After each edit, run the affected test suite and read the output "
            "before moving on.\n"
            "- Never report a task as done without pasting the passing test run.\n"
            "- A change with no verification output is not finished.\n"
        ),
    },
    "no_repeated_failing_command_loop": {
        "id": "rubric-no_repeated_failing_command_loop",
        "rationale": (
            "The tool re-ran the same failing command several times in a row "
            "instead of stopping to diagnose why it kept failing."
        ),
        "snippet": (
            "## Stop the Loop\n"
            "\n"
            "- If the same command fails twice in a row, stop and read the full "
            "error output before trying again.\n"
            "- Change the approach on the third attempt. Do not re-run the "
            "identical command a third time.\n"
        ),
    },
}

# Deterministic capability name -> CLAUDE.md fix. Only the capabilities that
# have a clear, actionable config-level remedy are covered here; the rest
# fall through (no prescription fires for them even below threshold).
CAPABILITY_PRESCRIPTIONS: dict[str, dict[str, str]] = {
    "completeness_tracking": {
        "id": "capability-completeness_tracking",
        "rationale": (
            "When a task lists several items to fix, the tool tends to stop after "
            "most of them instead of accounting for every one."
        ),
        "snippet": (
            "## Completeness Checklist\n"
            "\n"
            "- When a task lists N items to fix, search for all N instances first "
            "and write them down before making any change.\n"
            "- Work through the list one item at a time.\n"
            "- Search again after finishing and confirm zero instances remain "
            "before declaring the task done.\n"
        ),
    },
    "convention_adherence": {
        "id": "capability-convention_adherence",
        "rationale": (
            "New code does not match the style of the surrounding files (naming, "
            "imports, error handling), which shows up as review nitpicks."
        ),
        "snippet": (
            "## Match Existing Style\n"
            "\n"
            "- Before writing new code, read two or three neighboring files in the "
            "same module and match their naming, import order, and structure.\n"
            "- Do not introduce a new pattern when an existing one already covers "
            "the case.\n"
        ),
    },
    "refactoring_discipline": {
        "id": "capability-refactoring_discipline",
        "rationale": (
            "Refactors change observable behavior or skip parts of the test suite, "
            "so regressions slip through undetected."
        ),
        "snippet": (
            "## Refactoring Discipline\n"
            "\n"
            "- Refactors must be behavior-preserving. If a refactor changes output, "
            "that is a bug, not a refactor.\n"
            "- Run the whole test suite before and after, not just the tests you "
            "expect to touch.\n"
        ),
    },
    "security_awareness": {
        "id": "capability-security_awareness",
        "rationale": (
            "Security-sensitive tasks pass functional tests but leave common "
            "vulnerability patterns in place."
        ),
        "snippet": (
            "## Security Checklist\n"
            "\n"
            "- Check every change against: input validation, parameterized "
            "queries, secrets never hardcoded, HTTPS enforced, auth checks on "
            "every route.\n"
            "- Flag anything that touches auth, payments, or PII for extra review "
            "even if the tests pass.\n"
        ),
    },
}


def _grade_traces(
    results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
    run_dir: Path,
) -> tuple[dict[str, list[tuple[str, int]]], int, int]:
    """Grade every result's recorded trace, bucketed by rubric name.

    Returns (rubric_scores, n_graded, n_missing). A result counts as missing
    when it has no recorded trace, the trace file is absent, or the trace
    carries no gradeable spans (grade_trace_or_none returns None) — never
    faked as a passing score.
    """
    rubric_scores: dict[str, list[tuple[str, int]]] = defaultdict(list)
    n_graded = 0
    n_missing = 0

    for result in results:
        if not result.trace_path:
            n_missing += 1
            continue
        trace_path = run_dir / result.trace_path
        if not trace_path.exists():
            n_missing += 1
            continue

        task = task_defs.get(result.task_id)
        files_to_examine = task.files_to_examine if task else []
        scores = grade_trace_or_none(trace_path, files_to_examine=files_to_examine)
        if scores is None:
            n_missing += 1
            continue

        n_graded += 1
        for rubric_name, score in scores.items():
            rubric_scores[rubric_name].append((result.task_id, score))

    return rubric_scores, n_graded, n_missing


def _rubric_prescriptions(
    rubric_scores: dict[str, list[tuple[str, int]]],
) -> list[Prescription]:
    """A rubric fires a prescription when >= 2 tasks score below threshold."""
    prescriptions = []
    for rubric_name, task_scores in rubric_scores.items():
        spec = RUBRIC_PRESCRIPTIONS.get(rubric_name)
        if not spec:
            continue
        low = [(tid, sc) for tid, sc in task_scores if sc < RUBRIC_SCORE_THRESHOLD]
        if len(low) < RUBRIC_MIN_LOW_TASKS:
            continue
        prescriptions.append(
            Prescription(
                id=spec["id"],
                trigger=f"trace:{rubric_name}",
                evidence=[f"{tid}: scored {sc}" for tid, sc in low],
                affected_tasks=[tid for tid, _ in low],
                severity=len(low),
                snippet=spec["snippet"],
                rationale=spec["rationale"],
            )
        )
    return prescriptions


def _capability_task_scores(
    results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
    capability: str,
) -> list[tuple[str, float]]:
    scores = []
    for result in results:
        task = task_defs.get(result.task_id)
        if not task or capability not in task.capabilities:
            continue
        max_pts = result.outcome.partial_credit_max or 1
        pct = round((result.outcome.partial_credit_score / max_pts) * 100, 1)
        scores.append((result.task_id, pct))
    return scores


def _capability_prescriptions(
    results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
    threshold: int,
) -> list[Prescription]:
    """A capability fires when its mean score is below threshold on >= 2 tasks."""
    profile = compute_capability_profile(results, task_defs)
    prescriptions = []
    for cap_name, cap_score in profile.scores.items():
        spec = CAPABILITY_PRESCRIPTIONS.get(cap_name)
        if not spec:
            continue
        if cap_score.score is None or cap_score.tasks_tested < CAPABILITY_MIN_TASKS:
            continue
        if cap_score.score >= threshold:
            continue

        task_scores = _capability_task_scores(results, task_defs, cap_name)
        prescriptions.append(
            Prescription(
                id=spec["id"],
                trigger=f"capability:{cap_name}",
                evidence=[f"{tid}: scored {sc}" for tid, sc in task_scores],
                affected_tasks=[tid for tid, _ in task_scores],
                severity=round(threshold - cap_score.score),
                snippet=spec["snippet"],
                rationale=spec["rationale"],
            )
        )
    return prescriptions


def build_prescriptions(
    results: list[RunResult],
    task_defs: dict[str, TaskDefinition],
    run_dir: Path,
    threshold: int = CAPABILITY_SCORE_THRESHOLD,
) -> PrescriptionReport:
    """Turn trace-rubric failures and capability gaps into concrete config fixes.

    Trace files are located from each RunResult's own trace_path (the
    authoritative record written by the runner), not by re-parsing filenames
    in run_dir, so there is no separate trace-file-to-task-id mapping to keep
    in sync with the runner's naming convention.
    """
    tool = results[0].tool if results else ""

    rubric_scores, n_graded, n_missing = _grade_traces(results, task_defs, run_dir)

    prescriptions = _rubric_prescriptions(rubric_scores)
    prescriptions.extend(_capability_prescriptions(results, task_defs, threshold))
    prescriptions.sort(key=lambda p: -p.severity)

    return PrescriptionReport(
        tool=tool,
        prescriptions=prescriptions,
        n_traces_graded=n_graded,
        n_traces_missing=n_missing,
    )
