"""Grade a trace JSONL by 4 behavior dimensions, each 0-100.

These mirror the workflow disciplines that make AI coding agents reliable
in real shipping: read tests before editing, verify changes after editing,
respect scope, and don't loop on a failing command.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from awb.trace.jsonl import load_trace
from awb.trace.spans import FILE_EDIT, SHELL_COMMAND, TEST_RUN, TOOL_USE


def _attr(span: dict, key: str, default=""):
    return (span.get("attributes") or {}).get(key, default)


def _is_test_path(path: str) -> bool:
    norm = (path or "").lower().replace("\\", "/")
    parts = norm.split("/")
    if "tests" in parts or "test" in parts:
        return True
    return any(p.startswith("test_") or p.endswith("_test.py") for p in parts)


def _looks_like_test_command(cmd: str) -> bool:
    c = (cmd or "").lower()
    return (
        "pytest" in c
        or "npm test" in c
        or "go test" in c
        or "cargo test" in c
        or "rspec" in c
        or " test " in c
        or c.startswith("test ")
        or c.endswith(" test")
    )


def grade_trace(path: Path, files_to_examine: list[str] | None = None) -> dict[str, int]:
    """Score a trace.jsonl across 4 behavior dimensions, each 0-100."""
    spans = load_trace(path)
    return _grade_spans(spans, files_to_examine or [])


def _grade_spans(spans: list[dict], files_to_examine: list[str]) -> dict[str, int]:
    return {
        "read_tests_before_edit": _grade_read_tests_before_edit(spans),
        "ran_verification_after_change": _grade_ran_verification_after_change(spans),
        "no_out_of_scope_edits": _grade_no_out_of_scope_edits(spans, files_to_examine),
        "no_repeated_failing_command_loop": _grade_no_repeated_failing_loop(spans),
    }


def _has_gradeable_spans(spans: list[dict]) -> bool:
    """True if the trace contains behavior the rubrics can actually grade.

    A trace of only LLM_REQUEST spans (or no spans at all — e.g. a tool that
    runs without streaming tool events) carries nothing to grade. Those must
    report as n/a, not as a perfect 100 from the trivial-pass branches.
    """
    for s in spans:
        name = s.get("span_name")
        if name in (FILE_EDIT, SHELL_COMMAND, TEST_RUN):
            return True
        if name == TOOL_USE and (s.get("attributes") or {}).get("file.path"):
            return True
    return False


def grade_trace_or_none(
    path: Path, files_to_examine: list[str] | None = None
) -> dict[str, int] | None:
    """Grade a trace, or return None when it has no gradeable behavior.

    Use this anywhere a missing/span-less trace should surface as 'n/a' rather
    than a misleading perfect score (baseline export, leaderboard columns).
    """
    spans = load_trace(path)
    if not _has_gradeable_spans(spans):
        return None
    return _grade_spans(spans, files_to_examine or [])


def _grade_read_tests_before_edit(spans: Iterable[dict]) -> int:
    saw_test_read = False
    for s in spans:
        name = s.get("span_name")
        if name == TOOL_USE:
            tname = (_attr(s, "gen_ai.tool.name") or "").lower()
            fp = _attr(s, "file.path", "")
            if tname in {"read", "view", "open"} and _is_test_path(fp):
                saw_test_read = True
        elif name == FILE_EDIT:
            return 100 if saw_test_read else 0
    # No edits at all -> trivially passes
    return 100


def _grade_ran_verification_after_change(spans: Iterable[dict]) -> int:
    last_edit_idx = -1
    last_test_idx = -1
    for i, s in enumerate(spans):
        name = s.get("span_name")
        if name == FILE_EDIT:
            last_edit_idx = i
        elif name == TEST_RUN or (
            name == SHELL_COMMAND and _looks_like_test_command(_attr(s, "shell.command"))
        ):
            last_test_idx = i
    if last_edit_idx < 0:
        return 100
    return 100 if last_test_idx > last_edit_idx else 0


def _path_in_scope(path: str, allowed: list[str]) -> bool:
    """A path is in scope if it matches an allowed file exactly, or sits under
    an allowed directory entry (one written with a trailing slash, e.g. tests/)."""
    for a in allowed:
        if a.endswith("/"):
            if path == a.rstrip("/") or path.startswith(a):
                return True
        elif path == a:
            return True
    return False


def _grade_no_out_of_scope_edits(spans: Iterable[dict], files_to_examine: list[str]) -> int:
    if not files_to_examine:
        return 100
    edited = []
    for s in spans:
        if s.get("span_name") == FILE_EDIT:
            fp = _attr(s, "file.path", "")
            if fp:
                edited.append(fp)
    if not edited:
        return 100
    out_of_scope = sum(1 for e in edited if not _path_in_scope(e, files_to_examine))
    return max(0, round(100 * (1 - out_of_scope / len(edited))))


def _grade_no_repeated_failing_loop(spans: Iterable[dict]) -> int:
    """Penalize when the same failing shell command runs back-to-back.

    'worst' counts back-to-back repeats (so 3 identical failing commands
    in a row = worst=2, two repeats after the first attempt).
      worst 0 -> 100  (no repeated failing command)
      worst 1 -> 70   (one immediate retry)
      worst 2 -> 35   (loop of 3)
      worst 3+ -> 0   (loop of 4+ — clear thrashing)
    """
    last_cmd = None
    streak = 0
    worst = 0
    for s in spans:
        if s.get("span_name") != SHELL_COMMAND:
            continue
        exit_code = _attr(s, "shell.exit_code", 0)
        cmd = _attr(s, "shell.command", "")
        if exit_code != 0 and cmd == last_cmd:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
        last_cmd = cmd
    return max(0, 100 - worst * 35) if worst > 0 else 100
