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

# Lighthouse-style honesty rule: impact estimates are computed independently
# per prescription (mean shortfall below the firing threshold), so stacking
# several fixes does not mean their deltas add up. Surfaced in the report so
# a renderer prints it once next to the ranked list.
IMPACT_CAVEAT = "Impact estimates are independent; applying several fixes will not sum cleanly."


@dataclass
class Prescription:
    id: str
    trigger: str
    evidence: list[str]
    affected_tasks: list[str]
    severity: int
    snippet: str
    rationale: str
    estimated_score_delta: float | None = None


@dataclass
class PrescriptionReport:
    tool: str
    prescriptions: list[Prescription] = field(default_factory=list)
    n_traces_graded: int = 0
    n_traces_missing: int = 0
    caveat: str = IMPACT_CAVEAT


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
    "context_discipline": {
        "id": "rubric-context_discipline",
        "rationale": (
            "The tool read far more files than the task's declared scope "
            "justified, spending turns browsing instead of fixing the named files."
        ),
        "snippet": (
            "## Read With a Budget\n"
            "\n"
            "- Before exploring, list the files the task names as in scope. "
            "Read those first.\n"
            "- If a fix needs a file outside that list, say why before opening it.\n"
            "- Stop reading new files once you understand the change; do not keep "
            "browsing for context you already have.\n"
        ),
    },
    "tool_call_efficiency": {
        "id": "rubric-tool_call_efficiency",
        "rationale": (
            "The tool re-read the same file repeatedly, or re-edited the same "
            "file back to back with nothing run in between, which wastes turns "
            "without adding new information."
        ),
        "snippet": (
            "## Avoid Redundant Reads and Edits\n"
            "\n"
            "- Read a file once and hold onto what it said. Do not reopen a file "
            "you already read unless it changed.\n"
            "- After editing a file, run the affected tests or command before "
            "editing that same file again.\n"
            "- If a fix needs a follow-up edit, verify the first edit first.\n"
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
    "bug_diagnosis": {
        "id": "capability-bug_diagnosis",
        "rationale": (
            "The tool patches symptoms without tracing the failure back to a "
            "root cause, so the same bug resurfaces under a different input."
        ),
        "snippet": (
            "## Diagnose Before Patching\n"
            "\n"
            "- Reproduce the bug first. State the exact input and the exact "
            "wrong output.\n"
            "- Trace the wrong output back through the code to the single line "
            "that causes it before changing anything.\n"
            "- Fix the root cause, not the symptom. If the fix only hides a bad "
            "value instead of preventing it, keep looking.\n"
        ),
    },
    "multi_file_reasoning": {
        "id": "capability-multi_file_reasoning",
        "rationale": (
            "Changes touch only the file where the error appeared and miss the "
            "other files that share the same contract (callers, tests, config), "
            "leaving the codebase inconsistent."
        ),
        "snippet": (
            "## Trace the Full Change\n"
            "\n"
            "- Before editing, search for every caller, test, and config entry "
            "that references the function or field you are changing.\n"
            "- List every file that needs to change together, then edit all of "
            "them in the same pass.\n"
            "- A change that compiles but leaves one caller on the old contract "
            "is incomplete.\n"
        ),
    },
    "test_writing": {
        "id": "capability-test_writing",
        "rationale": (
            "New code ships without tests, or with tests that check the "
            "implementation instead of the behavior, so a later refactor cannot "
            "catch a regression."
        ),
        "snippet": (
            "## Write Tests That Catch Regressions\n"
            "\n"
            "- Every new function or bug fix gets a test that fails without the "
            "change and passes with it.\n"
            "- Test behavior and outputs, not internal method calls or "
            "implementation details.\n"
            "- Cover the failure case the bug report described, not only the "
            "happy path.\n"
        ),
    },
    "context_discovery": {
        "id": "capability-context_discovery",
        "rationale": (
            "The tool starts writing code before finding the existing pattern "
            "for the same problem, producing a second, inconsistent way of "
            "doing the same thing."
        ),
        "snippet": (
            "## Find the Existing Pattern First\n"
            "\n"
            "- Before adding new code, search the codebase for how the same "
            "kind of problem is already solved.\n"
            "- Reuse the existing helper, config, or convention instead of "
            "writing a new one.\n"
            "- If no existing pattern fits, say so before introducing a new one.\n"
        ),
    },
    "security_methodology": {
        "id": "capability-security_methodology",
        "rationale": (
            "Security-relevant changes are made ad hoc, with no repeatable "
            "check for the standard failure classes, so coverage depends on "
            "luck rather than a method."
        ),
        "snippet": (
            "## Security Review Pass\n"
            "\n"
            "- For any change touching auth, input parsing, or external data, "
            "check: injection, missing auth check, secret exposure, unsafe "
            "deserialization.\n"
            "- Name which of these apply and which do not in the summary of the "
            "change.\n"
            "- Do not mark a security-relevant task done without stating this "
            "pass was run.\n"
        ),
    },
    "code_comprehension": {
        "id": "capability-code_comprehension",
        "rationale": (
            "The tool edits code without first understanding what it currently "
            "does, producing a change that does not account for existing "
            "behavior or edge cases."
        ),
        "snippet": (
            "## Understand Before Editing\n"
            "\n"
            "- Read the full function or class you are about to change, not "
            "just the lines near the error.\n"
            "- State in your own words what the current code does before "
            "changing it.\n"
            "- If the current behavior is unclear, trace it through a concrete "
            "example first.\n"
        ),
    },
    "framework_knowledge": {
        "id": "capability-framework_knowledge",
        "rationale": (
            "Changes fight the framework instead of using its built-in "
            "mechanism, adding custom code where the framework already "
            "provides the feature."
        ),
        "snippet": (
            "## Use the Framework, Do Not Fight It\n"
            "\n"
            "- Before writing custom logic, check whether the framework already "
            "provides this (built-in validation, routing, lifecycle hook, ORM "
            "method).\n"
            "- Match the idioms already used elsewhere in this codebase for the "
            "same framework.\n"
            "- Only reach for a custom implementation when the framework has no "
            "supported way to do it.\n"
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
    carries no gradeable spans (grade_trace_or_none returns None) - never
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


def _mean_shortfall(scores: list, threshold: float) -> float | None:
    """Mean gap below the firing threshold, e.g. [40, 50] at threshold 60 -> 15.0.

    None when there is nothing to average (should not happen for a fired
    prescription, since firing requires >= 2 evidence tasks, but a prescription
    should never crash on the estimate rather than degrade to "not computable").
    """
    if not scores:
        return None
    return round(threshold - (sum(scores) / len(scores)), 1)


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
                estimated_score_delta=_mean_shortfall(
                    [sc for _, sc in low], RUBRIC_SCORE_THRESHOLD
                ),
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

        # Evidence and severity mirror the rubric path: only the tasks that
        # actually scored below threshold, and severity = how many, so the
        # two prescription types sort on one comparable unit.
        low = [
            (tid, sc)
            for tid, sc in _capability_task_scores(results, task_defs, cap_name)
            if sc < threshold
        ]
        prescriptions.append(
            Prescription(
                id=spec["id"],
                trigger=f"capability:{cap_name}",
                evidence=[f"{tid}: scored {sc}" for tid, sc in low],
                affected_tasks=[tid for tid, _ in low],
                severity=len(low),
                snippet=spec["snippet"],
                rationale=spec["rationale"],
                estimated_score_delta=_mean_shortfall([sc for _, sc in low], threshold),
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
    # Most severe first; within the same severity, the bigger estimated fix wins.
    prescriptions.sort(key=lambda p: (-p.severity, -(p.estimated_score_delta or 0)))

    return PrescriptionReport(
        tool=tool,
        prescriptions=prescriptions,
        n_traces_graded=n_graded,
        n_traces_missing=n_missing,
    )
